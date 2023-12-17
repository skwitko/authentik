"""Mobile authenticator stage"""
from json import dumps
from time import sleep
from typing import Optional
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import models
from django.http import HttpRequest
from django.utils.translation import gettext as __
from django.utils.translation import gettext_lazy as _
from django.views import View
from firebase_admin import credentials, initialize_app
from firebase_admin.exceptions import FirebaseError
from firebase_admin.messaging import (
    AndroidConfig,
    AndroidNotification,
    APNSConfig,
    APNSPayload,
    Aps,
    Message,
    Notification,
    send,
)
from rest_framework.serializers import BaseSerializer, Serializer
from structlog.stdlib import get_logger

from authentik.core.models import ExpiringModel, User
from authentik.core.types import UserSettingSerializer
from authentik.flows.models import ConfigurableStage, FriendlyNamedStage, Stage
from authentik.lib.generators import generate_code_fixed_length, generate_id
from authentik.lib.models import SerializerModel
from authentik.stages.authenticator.models import Device
from authentik.tenants.utils import DEFAULT_TENANT

LOGGER = get_logger()


def default_token_key():
    """Default token key"""
    return generate_id(40)


class ItemMatchingMode(models.TextChoices):
    """Configure which items the app shows the user, and what the user must select"""

    ACCEPT_DENY = "accept_deny"
    NUMBER_MATCHING_2 = "number_matching_2"
    NUMBER_MATCHING_3 = "number_matching_3"


class AuthenticatorMobileStage(ConfigurableStage, FriendlyNamedStage, Stage):
    """Setup Mobile authenticator devices"""

    item_matching_mode = models.TextField(
        choices=ItemMatchingMode.choices, default=ItemMatchingMode.NUMBER_MATCHING_3
    )
    firebase_config = models.JSONField(default=dict, help_text="temp")

    def create_transaction(self, device: "MobileDevice") -> "MobileTransaction":
        """Create a transaction for `device` with the config of this stage."""
        transaction = MobileTransaction(device=device)
        if self.item_matching_mode == ItemMatchingMode.ACCEPT_DENY:
            transaction.item_matching = [TransactionStates.ACCEPT, TransactionStates.DENY]
        if self.item_matching_mode == ItemMatchingMode.NUMBER_MATCHING_2:
            transaction.item_matching = [generate_code_fixed_length(2)] * 3
        if self.item_matching_mode == ItemMatchingMode.NUMBER_MATCHING_3:
            transaction.item_matching = [generate_code_fixed_length(3)] * 3
        transaction.save()
        return transaction

    @property
    def serializer(self) -> type[BaseSerializer]:
        from authentik.stages.authenticator_mobile.api.stage import (
            AuthenticatorMobileStageSerializer,
        )

        return AuthenticatorMobileStageSerializer

    @property
    def type(self) -> type[View]:
        from authentik.stages.authenticator_mobile.stage import AuthenticatorMobileStageView

        return AuthenticatorMobileStageView

    @property
    def component(self) -> str:
        return "ak-stage-authenticator-mobile-form"

    def ui_user_settings(self) -> Optional[UserSettingSerializer]:
        return UserSettingSerializer(
            data={
                "title": self.friendly_name or str(self._meta.verbose_name),
                "component": "ak-user-settings-authenticator-mobile",
            }
        )

    def __str__(self) -> str:
        return f"Mobile Authenticator Setup Stage {self.name}"

    class Meta:
        verbose_name = _("Mobile Authenticator Setup Stage")
        verbose_name_plural = _("Mobile Authenticator Setup Stages")


class MobileDevice(SerializerModel, Device):
    """Mobile authenticator for a single user"""

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    # Connect to the stage to when validating access we know the API Credentials
    stage = models.ForeignKey(AuthenticatorMobileStage, on_delete=models.CASCADE)

    device_id = models.TextField(unique=True)
    firebase_token = models.TextField(blank=True)

    state = models.JSONField(default=dict)
    last_checkin = models.DateTimeField(auto_now=True)

    def create_transaction(self) -> "MobileTransaction":
        """Create a transaction for this device with the config of its stage."""
        stage: AuthenticatorMobileStage = self.stage
        return stage.create_transaction(self)

    @property
    def serializer(self) -> Serializer:
        from authentik.stages.authenticator_mobile.api.device import MobileDeviceSerializer

        return MobileDeviceSerializer

    def __str__(self):
        return str(self.name) or str(self.user)

    class Meta:
        verbose_name = _("Mobile Device")
        verbose_name_plural = _("Mobile Devices")


class TransactionStates(models.TextChoices):
    """States a transaction can be in"""

    WAIT = "wait"
    ACCEPT = "accept"
    DENY = "deny"


class MobileTransaction(ExpiringModel):
    """A single push transaction"""

    tx_id = models.UUIDField(default=uuid4, primary_key=True)
    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE)
    decision_items = models.JSONField(default=list)
    correct_item = models.TextField()
    selected_item = models.TextField(default=None, null=True)

    @property
    def status(self) -> TransactionStates:
        """Get the status"""
        if not self.selected_item:
            return TransactionStates.WAIT
        if self.selected_item != self.correct_item:
            return TransactionStates.DENY
        return TransactionStates.ACCEPT

    def send_message(self, request: Optional[HttpRequest], **context):
        """Send mobile message"""
        app = initialize_app(
            credentials.Certificate(self.device.stage.firebase_config), name=str(self.tx_id)
        )
        branding = DEFAULT_TENANT.branding_title
        domain = ""
        if request:
            branding = request.tenant.branding_title
            domain = request.get_host()
        user: User = self.device.user
        message = Message(
            notification=Notification(
                title=__("%(brand)s authentication request" % {"brand": branding}),
                body=__(
                    "%(user)s is attempting to log in to %(domain)s"
                    % {
                        "user": user.username,  # pylint: disable=no-member
                        "domain": domain,
                    }
                ),
            ),
            android=AndroidConfig(
                priority="normal",
                notification=AndroidNotification(icon="stock_ticker_update", color="#f45342"),
                data={
                    "tx_id": str(self.tx_id),
                    "user_decision_items": dumps(self.item_matching),
                },
            ),
            apns=APNSConfig(
                headers={"apns-push-type": "alert", "apns-priority": "10"},
                payload=APNSPayload(
                    aps=Aps(
                        badge=0,
                        sound="default",
                        content_available=True,
                        category="cat_authentik_push_authorization",
                    ),
                    interruption_level="time-sensitive",
                    tx_id=str(self.tx_id),
                    user_decision_items=self.item_matching,
                ),
            ),
            token=self.device.firebase_token,
        )
        try:
            response = send(message, app=app)
            LOGGER.debug("Sent notification", id=response)
        except (ValueError, FirebaseError) as exc:
            LOGGER.warning("failed to push", exc=exc)
        return True

    def wait_for_response(self, max_checks=30) -> TransactionStates:
        """Wait for a change in status"""
        checks = 0
        while True:
            self.refresh_from_db()
            if self.status in [TransactionStates.ACCEPT, TransactionStates.DENY]:
                self.delete()
                return self.status
            checks += 1
            if checks > max_checks:
                self.delete()
                raise TimeoutError()
            sleep(1)


class MobileDeviceToken(ExpiringModel):
    """Mobile device token"""

    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    token = models.TextField(default=default_token_key)

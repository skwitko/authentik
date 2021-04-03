import { t } from "@lingui/macro";
import { customElement, html, property, TemplateResult } from "lit-element";
import { AKResponse } from "../../api/Client";
import { Table, TableColumn } from "../table/Table";

import "../forms/DeleteForm";
import { PAGE_SIZE } from "../../constants";
import { ExpiringBaseGrantModel, Oauth2Api } from "authentik-api";
import { DEFAULT_CONFIG } from "../../api/Config";

@customElement("ak-user-oauth-refresh-list")
export class UserOAuthRefreshList extends Table<ExpiringBaseGrantModel> {
    @property()
    userId?: string;

    apiEndpoint(page: number): Promise<AKResponse<ExpiringBaseGrantModel>> {
        return new Oauth2Api(DEFAULT_CONFIG).oauth2RefreshTokensList({
            user: this.userId,
            ordering: "expires",
            page: page,
            pageSize: PAGE_SIZE,
        });
    }

    order = "-expires";

    columns(): TableColumn[] {
        return [
            new TableColumn(t`Provider`, t`provider`),
            new TableColumn(t`Expires`, t`expires`),
            new TableColumn(t`Scopes`, t`scope`),
            new TableColumn(""),
        ];
    }

    row(item: ExpiringBaseGrantModel): TemplateResult[] {
        return [
            html`${item.provider.name}`,
            html`${item.expires?.toLocaleString()}`,
            html`${item.scope.join(", ")}`,
            html`
            <ak-forms-delete
                .obj=${item}
                objectLabel=${t`Refresh Code`}
                .delete=${() => {
                    return new Oauth2Api(DEFAULT_CONFIG).oauth2RefreshTokensDelete({
                        id: item.pk || 0,
                    });
                }}>
                <button slot="trigger" class="pf-c-button pf-m-danger">
                    ${t`Delete Refresh Code`}
                </button>
            </ak-forms-delete>`,
        ];
    }

}

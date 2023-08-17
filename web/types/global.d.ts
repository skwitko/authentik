declare module "*.css";
declare module "*.md" {
    const html: string;
    const metadata: { [key: string]: string };
    const filename: string;
}

declare namespace Intl {
    class ListFormat {
        constructor(locale: string, args: { [key: string]: string });
        public format: (items: string[]) => string;
    }
}

declare global {
    // TODO should remove in next TypeScript version
    interface Document {
        startViewTransition(callback?: () => void | Promise<void>): ViewTransition;
    }

    interface ViewTransition {
        finished: Promise<void>;
        ready: Promise<void>;
        updateCallbackDone: () => void;
        skipTransition(): void;
    }
}

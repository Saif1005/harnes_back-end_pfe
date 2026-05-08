/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_HARNESS_URL?: string;
  /** Cible locale pour vite proxy `/harness-proxy` (sans toucher `.env`). */
  readonly VITE_HARNESS_DEV_TARGET?: string;
  readonly VITE_GOOGLE_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  google?: {
    accounts?: {
      id?: {
        initialize: (cfg: {
          client_id: string;
          callback: (resp: { credential?: string }) => void;
        }) => void;
        renderButton: (
          parent: HTMLElement,
          options: {
            type?: string;
            shape?: string;
            theme?: string;
            text?: string;
            size?: string;
            locale?: string;
            width?: number;
          }
        ) => void;
      };
    };
  };
}

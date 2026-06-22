/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_WALLPAPER_API_URL?: string;
  readonly VITE_WALLPAPER_FALLBACK_URLS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

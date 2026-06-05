import { useEffect } from "react";

type PicsumPhoto = {
  id: string;
  author: string;
  width: number;
  height: number;
  url: string;
};

type CachedWallpaper = {
  apiUrl: string;
  imageUrl: string;
  author?: string;
  sourceUrl?: string;
};

const CACHE_KEY = "dailychewer_wallpaper_backdrop";
const DEFAULT_WALLPAPER_API_URL = "https://picsum.photos/v2/list?page=2&limit=100";

function todayKey() {
  return new Date().toISOString().slice(0, 10);
}

function applyWallpaper(imageUrl: string) {
  document.documentElement.style.setProperty("--wallpaper-image", `url("${imageUrl}")`);
  document.documentElement.dataset.wallpaper = "ready";
}

function preloadImage(imageUrl: string) {
  return new Promise<void>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("Wallpaper image failed to load."));
    image.decoding = "async";
    image.src = imageUrl;
  });
}

function readCachedWallpaper(apiUrl: string): CachedWallpaper | null {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) {
      return null;
    }
    const cached = JSON.parse(raw) as CachedWallpaper;
    return cached.apiUrl === apiUrl && cached.imageUrl ? cached : null;
  } catch {
    return null;
  }
}

function writeCachedWallpaper(payload: CachedWallpaper) {
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
  } catch {
    // localStorage can be disabled; the wallpaper should still apply for this session.
  }
}

function fallbackImageUrl(date: string) {
  return `https://picsum.photos/seed/dailychewer-landscape-${date}/1920/1080`;
}

export function WallpaperBackdrop() {
  useEffect(() => {
    const date = todayKey();
    const apiUrl = import.meta.env.VITE_WALLPAPER_API_URL || DEFAULT_WALLPAPER_API_URL;
    const cached = readCachedWallpaper(apiUrl);
    let cancelled = false;
    document.documentElement.dataset.wallpaper = "loading";

    async function loadWallpaper() {
      try {
        const response = await fetch(apiUrl);
        if (!response.ok) {
          throw new Error(`Wallpaper API returned ${response.status}`);
        }
        const photos = (await response.json()) as PicsumPhoto[];
        const landscapePhotos = photos.filter((photo) => photo.width >= photo.height);
        const candidates = landscapePhotos.length ? landscapePhotos : photos;
        const selected = candidates[Math.floor(Math.random() * candidates.length)];
        if (!selected) {
          throw new Error("Wallpaper API returned no photos.");
        }
        const imageUrl = `https://picsum.photos/id/${selected.id}/1920/1080`;
        await preloadImage(imageUrl);
        if (cancelled) {
          return;
        }
        applyWallpaper(imageUrl);
        writeCachedWallpaper({
          apiUrl,
          imageUrl,
          author: selected.author,
          sourceUrl: selected.url,
        });
      } catch {
        const imageUrl = cached?.imageUrl || fallbackImageUrl(`${date}-${Date.now()}`);
        try {
          await preloadImage(imageUrl);
        } catch {
          return;
        }
        if (cancelled) {
          return;
        }
        applyWallpaper(imageUrl);
        writeCachedWallpaper({ apiUrl, imageUrl });
      }
    }

    void loadWallpaper();

    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}

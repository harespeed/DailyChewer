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
const DEFAULT_WALLPAPER_FALLBACK_URLS = [
  "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1920&q=80",
  "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1920&q=80",
  "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1920&q=80",
  "https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=1920&q=80",
  "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1920&q=80",
  "https://images.unsplash.com/photo-1433086966358-54859d0ed716?auto=format&fit=crop&w=1920&q=80",
  "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1920&q=80",
  "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=1920&q=80",
  "https://loremflickr.com/1920/1080/landscape,nature?lock={seed}",
  "https://picsum.photos/seed/dailychewer-landscape-{seed}/1920/1080",
];

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

function fallbackImageUrls(seed: string) {
  const configuredUrls = import.meta.env.VITE_WALLPAPER_FALLBACK_URLS?.split(",")
    .map((url) => url.trim())
    .filter(Boolean);
  const urls = configuredUrls?.length ? configuredUrls : DEFAULT_WALLPAPER_FALLBACK_URLS;
  return shuffle(urls).map((url) => url.split("{seed}").join(encodeURIComponent(seed)));
}

function shuffle<T>(items: T[]) {
  const shuffled = [...items];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

async function preloadFirstAvailableImage(imageUrls: string[]) {
  for (const imageUrl of imageUrls) {
    try {
      await preloadImage(imageUrl);
      return imageUrl;
    } catch {
      // Try the next remote wallpaper source.
    }
  }
  return null;
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
        const seed = `${date}-${Date.now()}`;
        const imageUrl = await preloadFirstAvailableImage([
          ...fallbackImageUrls(seed),
          ...(cached?.imageUrl ? [cached.imageUrl] : []),
        ]);
        if (!imageUrl) {
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

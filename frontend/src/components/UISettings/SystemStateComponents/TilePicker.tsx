import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { FaMinus, FaPlus } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

/**
 * A small slippy map for picking coordinates, with no mapping library.
 *
 * Leaflet would be the obvious choice and is about 45 kB of JavaScript for
 * markers, popups, layers and a plugin system this page never touches. What it
 * actually needs is the Web Mercator tile maths below — some forty lines — plus
 * a drag handler. So there is no dependency, nothing to keep on a supply-chain
 * watch list, and nothing that can break on a version bump.
 *
 * The centre of the box *is* the selection. That removes the marker, the
 * dragging of the marker, and the question of what happens when you drag the
 * map instead of the marker.
 *
 * Tiles are fetched by the browser, so this works against a controller with no
 * route to the internet. When the browser has none either, every tile fails to
 * load and the component says so rather than showing a grey void.
 */

const TILE_SIZE = 256;
const MIN_ZOOM = 2;
const MAX_ZOOM = 18;
/** Web Mercator is undefined at the poles; this is the usual cut-off. */
const MAX_LATITUDE = 85.05112878;

const lonToX = (lon: number, zoom: number) => ((lon + 180) / 360) * 2 ** zoom;

const latToY = (lat: number, zoom: number) => {
  const clamped = Math.max(-MAX_LATITUDE, Math.min(MAX_LATITUDE, lat));
  const sin = Math.sin((clamped * Math.PI) / 180);
  return (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * 2 ** zoom;
};

const xToLon = (x: number, zoom: number) => (x / 2 ** zoom) * 360 - 180;

const yToLat = (y: number, zoom: number) => {
  const n = Math.PI - (2 * Math.PI * y) / 2 ** zoom;
  return (180 / Math.PI) * Math.atan(Math.sinh(n));
};

const wrapLon = (lon: number) => ((((lon + 180) % 360) + 360) % 360) - 180;

interface TilePickerProps {
  /** Currently selected latitude, or null when nothing is set yet. */
  latitude: number | null;
  /** Currently selected longitude, or null when nothing is set yet. */
  longitude: number | null;
  /** Called with the new centre after a pan or zoom settles. */
  onPick: (latitude: number, longitude: number) => void;
  /** Height of the map box in pixels. */
  height?: number;
}

export default function TilePicker({
  latitude,
  longitude,
  onPick,
  height = 300,
}: TilePickerProps) {
  const { t } = useTranslation();
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height });
  const [zoom, setZoom] = useState(latitude === null ? 4 : 11);
  const [centre, setCentre] = useState({
    lat: latitude ?? 52,
    lon: longitude ?? 19,
  });
  const [failed, setFailed] = useState(0);
  const [loaded, setLoaded] = useState(0);

  // Follow the numeric fields when they are edited by hand, but not while the
  // map itself is what changed them — `dragging` guards that round trip.
  const dragging = useRef(false);
  useLayoutEffect(() => {
    if (dragging.current || latitude === null || longitude === null) return;
    setCentre((current) =>
      Math.abs(current.lat - latitude) < 1e-6 && Math.abs(current.lon - longitude) < 1e-6
        ? current
        : { lat: latitude, lon: longitude },
    );
  }, [latitude, longitude]);

  // Measured before paint, not after: the tile grid cannot be laid out without
  // a width, and waiting for a ResizeObserver callback leaves one empty frame
  // — or, if the observer never fires because the box was already its final
  // size, an empty map.
  useLayoutEffect(() => {
    const box = boxRef.current;
    if (!box) return;

    const measure = () => {
      setSize((current) =>
        current.width === box.clientWidth && current.height === box.clientHeight
          ? current
          : { width: box.clientWidth, height: box.clientHeight },
      );
    };
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  /** Tiles covering the viewport, with their pixel offsets inside the box. */
  const tiles = useMemo(() => {
    if (size.width === 0) return [];
    const scale = 2 ** zoom;
    const left = lonToX(centre.lon, zoom) * TILE_SIZE - size.width / 2;
    const top = latToY(centre.lat, zoom) * TILE_SIZE - size.height / 2;

    const firstX = Math.floor(left / TILE_SIZE);
    const firstY = Math.floor(top / TILE_SIZE);
    const countX = Math.ceil(size.width / TILE_SIZE) + 1;
    const countY = Math.ceil(size.height / TILE_SIZE) + 1;

    const result: { key: string; url: string; left: number; top: number }[] = [];
    for (let ix = 0; ix < countX; ix++) {
      for (let iy = 0; iy < countY; iy++) {
        const tx = firstX + ix;
        const ty = firstY + iy;
        // Vertically there is nothing above the north pole or below the south.
        if (ty < 0 || ty >= scale) continue;
        // Horizontally the world repeats, so wrap instead of leaving a gap.
        const wrapped = ((tx % scale) + scale) % scale;
        result.push({
          key: `${zoom}/${tx}/${ty}`,
          url: `https://tile.openstreetmap.org/${zoom}/${wrapped}/${ty}.png`,
          left: tx * TILE_SIZE - left,
          top: ty * TILE_SIZE - top,
        });
      }
    }
    return result;
  }, [centre, zoom, size]);

  const moveBy = useCallback(
    (dx: number, dy: number) => {
      setCentre((current) => {
        const x = lonToX(current.lon, zoom) * TILE_SIZE - dx;
        const y = latToY(current.lat, zoom) * TILE_SIZE - dy;
        return {
          lat: yToLat(y / TILE_SIZE, zoom),
          lon: wrapLon(xToLon(x / TILE_SIZE, zoom)),
        };
      });
    },
    [zoom],
  );

  const commit = useCallback(() => {
    onPick(centre.lat, centre.lon);
  }, [centre, onPick]);

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    let lastX = event.clientX;
    let lastY = event.clientY;

    const onMove = (move: PointerEvent) => {
      moveBy(move.clientX - lastX, move.clientY - lastY);
      lastX = move.clientX;
      lastY = move.clientY;
    };
    const onUp = () => {
      target.removeEventListener('pointermove', onMove);
      target.removeEventListener('pointerup', onUp);
      target.removeEventListener('pointercancel', onUp);
      dragging.current = false;
      // Read the centre from state on the next tick: `centre` captured in this
      // closure is the value from before the drag.
      setCentre((current) => {
        onPick(current.lat, current.lon);
        return current;
      });
    };
    target.addEventListener('pointermove', onMove);
    target.addEventListener('pointerup', onUp);
    target.addEventListener('pointercancel', onUp);
  };

  const changeZoom = (delta: number) => {
    setZoom((current) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, current + delta)));
  };

  // Every tile failing means no route to the tile server from this browser.
  const offline = tiles.length > 0 && loaded === 0 && failed >= tiles.length;

  return (
    <div className="space-y-1">
      <div
        ref={boxRef}
        className="relative overflow-hidden rounded-lg border border-base-300 bg-base-200 cursor-grab active:cursor-grabbing touch-none select-none"
        style={{ height }}
        onPointerDown={onPointerDown}
      >
        {tiles.map((tile) => (
          <img
            key={tile.key}
            src={tile.url}
            alt=""
            draggable={false}
            width={TILE_SIZE}
            height={TILE_SIZE}
            className="absolute pointer-events-none"
            style={{ left: tile.left, top: tile.top }}
            onLoad={() => setLoaded((n) => n + 1)}
            onError={() => setFailed((n) => n + 1)}
          />
        ))}

        {/* The centre of the box is the selection — hence a crosshair and no
            marker to drag. */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-6 h-6 rounded-full border-2 border-error bg-error/20 shadow" />
        </div>

        <div className="absolute top-2 right-2 flex flex-col gap-1">
          <button
            type="button"
            className="btn btn-xs btn-square"
            onClick={() => changeZoom(1)}
            disabled={zoom >= MAX_ZOOM}
            title={t('location.map_zoom_in')}
          >
            <FaPlus className="w-2.5 h-2.5" />
          </button>
          <button
            type="button"
            className="btn btn-xs btn-square"
            onClick={() => changeZoom(-1)}
            disabled={zoom <= MIN_ZOOM}
            title={t('location.map_zoom_out')}
          >
            <FaMinus className="w-2.5 h-2.5" />
          </button>
        </div>

        {offline && (
          <div className="absolute inset-0 flex items-center justify-center bg-base-200/90 p-4">
            <p className="text-xs text-center opacity-70">{t('location.map_unavailable')}</p>
          </div>
        )}

        {/* Required by the OpenStreetMap tile usage policy. */}
        <div className="absolute bottom-0 right-0 bg-base-100/80 text-[10px] px-1 rounded-tl">
          ©{' '}
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noreferrer noopener"
            className="link"
          >
            OpenStreetMap
          </a>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-xs opacity-60">{t('location.map_hint')}</span>
        <button type="button" className="btn btn-xs" onClick={commit}>
          {t('location.map_use_centre')}
        </button>
      </div>
    </div>
  );
}

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import uPlot from 'uplot';

/**
 * Generic history data point for sparkline charts.
 * Can be used by any component that tracks value history over time.
 */
export interface HistoryPoint {
  timestamp: number;
  value: number;
}

interface SparklineProps {
  /** Array of time-series data points */
  points: HistoryPoint[];
  /** Stroke color for the line (default: sky-600) */
  strokeColor?: string;
  /** Fill color with opacity (default: semi-transparent blue) */
  fillColor?: string;
}

/**
 * LTTB (Largest Triangle Three Buckets) downsampling.
 *
 * Reduces the number of data points while preserving the visual shape
 * of the chart. Keeps first and last points, then selects the most
 * visually significant point in each bucket.
 */
function downsampleLTTB(
  points: HistoryPoint[],
  targetCount: number,
): HistoryPoint[] {
  if (points.length <= targetCount || targetCount < 3) return points;

  const result: HistoryPoint[] = [points[0]]; // Always keep first
  const bucketSize = (points.length - 2) / (targetCount - 2);

  let prevIndex = 0;

  for (let i = 0; i < targetCount - 2; i++) {
    const rangeStart = Math.floor((i + 0) * bucketSize) + 1;
    const rangeEnd = Math.min(Math.floor((i + 1) * bucketSize) + 1, points.length - 1);

    // Average of next bucket (for triangle area calculation)
    const nextStart = Math.floor((i + 1) * bucketSize) + 1;
    const nextEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, points.length - 1);
    let avgX = 0;
    let avgY = 0;
    const nextCount = nextEnd - nextStart;
    for (let j = nextStart; j < nextEnd; j++) {
      avgX += points[j].timestamp;
      avgY += points[j].value;
    }
    if (nextCount > 0) {
      avgX /= nextCount;
      avgY /= nextCount;
    }

    // Find point in current bucket with largest triangle area
    let maxArea = -1;
    let bestIndex = rangeStart;
    const prevPoint = points[prevIndex];

    for (let j = rangeStart; j < rangeEnd; j++) {
      const area = Math.abs(
        (prevPoint.timestamp - avgX) * (points[j].value - prevPoint.value) -
        (prevPoint.timestamp - points[j].timestamp) * (avgY - prevPoint.value),
      );
      if (area > maxArea) {
        maxArea = area;
        bestIndex = j;
      }
    }

    result.push(points[bestIndex]);
    prevIndex = bestIndex;
  }

  result.push(points[points.length - 1]); // Always keep last
  return result;
}

function SparklineBase({ points, strokeColor = '#0284c7', fillColor = 'rgba(96, 165, 250, 0.10)' }: SparklineProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<uPlot | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  // Downsample points based on chart width (1 point per 2 pixels max)
  const displayPoints = useMemo(() => {
    const maxPoints = Math.max(size.width > 0 ? Math.floor(size.width / 2) : 80, 20);
    return downsampleLTTB(points, maxPoints);
  }, [points, size.width]);

  const pointsRef = useRef(displayPoints);
  pointsRef.current = displayPoints;

  const data = useMemo<uPlot.AlignedData>(() => {
    const xValues = displayPoints.map((point) => point.timestamp * 1000);
    const yValues = displayPoints.map((point) => point.value);
    return [xValues, yValues];
  }, [displayPoints]);

  useEffect(() => {
    if (!wrapperRef.current) {
      return;
    }

    const element = wrapperRef.current;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }

      const nextWidth = Math.floor(entry.contentRect.width);
      const nextHeight = Math.floor(entry.contentRect.height);

      setSize((current) => {
        if (current.width === nextWidth && current.height === nextHeight) {
          return current;
        }

        return {
          width: nextWidth,
          height: nextHeight,
        };
      });
    });

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, []);

  const options = useMemo<uPlot.Options>(() => ({
    width: size.width,
    height: size.height,
    legend: { show: false },
    cursor: { show: false },
    scales: {
      x: { time: false },
      y: { auto: true },
    },
    axes: [
      {
        show: false,
      },
      {
        show: false,
      },
    ],
    series: [
      {},
      {
        stroke: strokeColor,
        width: 2,
        fill: fillColor,
      },
    ],
    padding: [8, 8, 8, 8],
  }), [size.height, size.width, strokeColor, fillColor]);

  useEffect(() => {
    if (!chartContainerRef.current || size.width <= 0 || size.height <= 0) {
      return;
    }

    if (!chartRef.current) {
      chartRef.current = new uPlot(options, data, chartContainerRef.current);
      return;
    }

    if (chartRef.current.width !== size.width || chartRef.current.height !== size.height) {
      chartRef.current.setSize({ width: size.width, height: size.height });
    }

    chartRef.current.setData(data, true);
  }, [data, options, size.height, size.width]);

  useEffect(() => {
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const chart = chartRef.current;
    const wrapper = wrapperRef.current;
    if (!chart || !wrapper) return;

    const rect = wrapper.getBoundingClientRect();
    const x = e.clientX - rect.left;

    // Find the nearest data index by converting pixel position to value
    const xVal = chart.posToVal(x, 'x');
    const xs = chart.data[0];
    if (!xs || xs.length === 0) return;

    // Binary search for nearest index
    let lo = 0;
    let hi = xs.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (xs[mid] < xVal) lo = mid + 1;
      else hi = mid;
    }
    // Check if the previous index is closer
    if (lo > 0 && Math.abs(xs[lo - 1] - xVal) < Math.abs(xs[lo] - xVal)) {
      lo--;
    }

    const idx = lo;
    const val = chart.data[1][idx];
    if (val == null) return;

    const tt = tooltipRef.current;
    if (!tt) return;

    const posX = chart.valToPos(xs[idx], 'x');
    const posY = chart.valToPos(val, 'y');
    const pts = pointsRef.current;
    const ts = pts[idx]?.timestamp ?? 0;
    const time = new Date(ts * 1000).toLocaleTimeString();

    tt.textContent = `${val.toFixed(2)} · ${time}`;
    tt.style.display = '';
    tt.style.left = `${posX}px`;
    tt.style.top = `${Math.max(posY - 28, 2)}px`;
  }, []);

  const handleMouseLeave = useCallback(() => {
    const tt = tooltipRef.current;
    if (tt) tt.style.display = 'none';
  }, []);

  return (
    <div
      ref={wrapperRef}
      className="sparkline-chart h-full w-full"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      <div ref={chartContainerRef} className="absolute inset-0" />
      <div
        ref={tooltipRef}
        className="absolute z-50 rounded bg-gray-900/90 px-1.5 py-0.5 text-[10px] text-white shadow-lg whitespace-nowrap pointer-events-none"
        style={{ display: 'none', transform: 'translateX(-50%)' }}
      />
    </div>
  );
}

const Sparkline = memo(SparklineBase);

export default Sparkline;

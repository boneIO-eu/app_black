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

function SparklineBase({ points, strokeColor = '#0284c7', fillColor = 'rgba(96, 165, 250, 0.10)' }: SparklineProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<uPlot | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const pointsRef = useRef(points);
  pointsRef.current = points;
  const [size, setSize] = useState({ width: 0, height: 0 });

  const data = useMemo<uPlot.AlignedData>(() => {
    const xValues = points.map((point) => point.timestamp * 1000);
    const yValues = points.map((point) => point.value);
    return [xValues, yValues];
  }, [points]);

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

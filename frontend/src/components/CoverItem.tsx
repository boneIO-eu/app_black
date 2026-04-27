import React, { memo, useState, useEffect, useCallback, useRef } from "react";
import { MdBlinds, MdBlindsClosed } from "react-icons/md";
import axios from "@/api/axios";
import { formatTimestamp } from '../utils/formatters';
import { FaStop } from 'react-icons/fa';
import { LuArrowDownNarrowWide, LuArrowUpNarrowWide, LuArrowDownLeft, LuArrowUpRight } from "react-icons/lu";
import { CoverState } from "@/hooks/useWebSocket";
import { useTranslation } from '@/hooks/useTranslation';
import { cn } from "@/lib/utils";


interface CoverItemProps {
  cover: CoverState;
  action: (id: string, name: string, action: string) => void;
  isGrid: boolean;
  error: string | null;
  onLongPress?: (cover: CoverState) => void;
}

const CoverItem: React.FC<CoverItemProps> = memo(({ cover, action, isGrid, error, onLongPress }) => {
  const { t } = useTranslation();

  // Long press handling
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isLongPress = useRef(false);

  const handlePressStart = (e: React.MouseEvent | React.TouchEvent) => {
    if (!onLongPress) return;
    // Don't trigger long press when interacting with sliders
    const target = e.target as HTMLElement;
    if (target.tagName === 'INPUT' && (target as HTMLInputElement).type === 'range') return;
    isLongPress.current = false;
    longPressTimer.current = setTimeout(() => {
      isLongPress.current = true;
      onLongPress(cover);
    }, 500);
  };

  const handlePressEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  // Main position slider
  const Icon = cover.state === 'open' ? MdBlinds : MdBlindsClosed;
  const [sliderPosition, setSliderPosition] = useState<number>(cover.position);
  const [isSliderActive, setIsSliderActive] = useState<boolean>(false);

  // Venetian tilt slider
  const [tilt, setTilt] = useState<number>(cover.tilt ?? 0);
  const isVenetian = cover.kind === 'venetian';
  const [isTiltActive, setIsTiltActive] = useState<boolean>(false);

  // Sync tilt state with prop
  useEffect(() => {
    if (!isTiltActive && typeof cover.tilt === 'number') {
      setTilt(cover.tilt);
    }
  }, [cover.tilt, isTiltActive]);

  // Update slider position when cover position changes (if not actively sliding)
  useEffect(() => {
    if (!isSliderActive) {
      setSliderPosition(cover.position);
    }
  }, [cover.position, isSliderActive]);

  // Debounce function for setting position
  const debouncedSetPosition = useCallback(() => {
    const timer = setTimeout(() => {
      if (sliderPosition !== cover.position) {
        axios.post(`/api/covers/${cover.id}/set_position`, { position: sliderPosition })
          .catch(error => console.error('Error setting cover position:', error));
      }
      setIsSliderActive(false);
    }, 300); // 0.3 second debounce
    return () => clearTimeout(timer);
  }, [sliderPosition, cover.id, cover.position]);

  // Debounce function for setting tilt
  const debouncedSetTilt = useCallback(() => {
    const timer = setTimeout(() => {
      if (typeof cover.tilt === 'number' && tilt !== cover.tilt) {
        axios.post(`/api/covers/${cover.id}/set_tilt`, { tilt })
          .catch(error => console.error('Error setting tilt:', error));
      }
      setIsTiltActive(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [tilt, cover.id, cover.tilt]);

  // Set up debounce effect
  useEffect(() => {
    if (isSliderActive) {
      return debouncedSetPosition();
    }
  }, [isSliderActive, sliderPosition, debouncedSetPosition]);

  // Set up debounce effect for tilt
  useEffect(() => {
    if (isTiltActive) {
      return debouncedSetTilt();
    }
  }, [isTiltActive, tilt, debouncedSetTilt]);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newPosition = parseInt(e.target.value, 10);
    setSliderPosition(newPosition);
    setIsSliderActive(true);
  };

  const handleTiltChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTilt = parseInt(e.target.value, 10);
    setTilt(newTilt);
    setIsTiltActive(true);
  };

  // Tilt stepper for venetian
  const handleTilt = (target: number) => {
    setTilt(target);
    setIsTiltActive(true);
  };


  return (
    <div
      className={`bg-base-100 shadow-sm rounded-lg p-4 ${isGrid ? '' : 'flex justify-between items-center'} ${onLongPress ? 'cursor-pointer' : ''}`}
      onMouseDown={handlePressStart}
      onMouseUp={handlePressEnd}
      onMouseLeave={handlePressEnd}
      onTouchStart={handlePressStart}
      onTouchEnd={handlePressEnd}
      title={onLongPress ? t('outputs.long_press_to_edit') : undefined}
    >
      <div className={`flex items-center justify-between gap-2 min-w-0 ${isGrid ? 'mb-3' : ''}`}>
        <div className="flex items-center gap-2 min-w-0">
          <Icon className={`text-xl shrink-0 ${cover.state === 'open' ? 'text-yellow-400' : 'text-gray-400'}`} />
          <span className="text-lg truncate" title={cover.name}>{cover.name}</span>
        </div>
      </div>
      <div className={`${isGrid ? 'mt-3' : 'flex flex-col items-end gap-2 min-w-64'}`}>
        <div className="flex gap-2">
          <button
            className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => action(cover.id, cover.name, 'open')}
            disabled={error !== null || cover.current_operation === 'opening' || (cover.state === 'open' && cover.position === 100)}
          >
            <LuArrowUpNarrowWide />
          </button>
          <button
            className="px-3 py-1 bg-gray-500 hover:bg-gray-600 text-white rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => action(cover.id, cover.name, 'stop')}
            disabled={error !== null || cover.current_operation === 'idle'}
          >
            <FaStop />
          </button>
          <button
            className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => action(cover.id, cover.name, 'close')}
            disabled={error !== null || cover.current_operation === 'closing' || (cover.state === 'closed' && cover.position === 0)}
          >
            <LuArrowDownNarrowWide />
          </button>
          {isVenetian &&
            (<>
              <button
                className="px-3 py-1 bg-purple-500 hover:bg-purple-600 text-white rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => handleTilt(0)}
                disabled={error !== null || cover.current_operation !== 'idle'}
                title={t('covers.tilt_down')}
              >
                <LuArrowDownLeft />
              </button>
              <button
                className="px-3 py-1 bg-purple-500 hover:bg-purple-600 text-white rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => handleTilt(100)}
                disabled={error !== null || cover.current_operation !== 'idle'}
                title={t('covers.tilt_up')}
              >
                <LuArrowUpRight />
              </button>
            </>)
          }
        </div>

        <div className="w-full mt-3 bg-secondary p-2 rounded-lg">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>0%</span>
            {isSliderActive && <span className="font-semibold text-primary">{sliderPosition}%</span>}
            <span>100%</span>
          </div>
          <div className="relative pt-1">
            <input
              type="range"
              min="0"
              max="100"
              value={sliderPosition}
              onChange={handleSliderChange}
              disabled={error !== null || cover.current_operation !== 'idle'}
              className="range range-sm range-primary [--range-bg:orange] [--range-thumb:blue]"
            />
          </div>

          {/* TiltBar pod głównym sliderem */}
          {isVenetian && (
            <>
              {isTiltActive && (
                <div className="text-xs text-center font-semibold text-accent mt-1">
                  {t('covers.tilt')}: {tilt}%
                </div>
              )}
              <input
                type="range"
                min="0"
                max="100"
                value={tilt}
                onChange={handleTiltChange}
                disabled={error !== null || cover.current_operation !== 'idle'}
                className="range range-xs range-accent mt-1"
                style={{
                  width: '100%',
                  background: 'repeating-linear-gradient(90deg, #eee, #eee 8px, #fff 8px, #fff 16px)'
                }}
              />
            </>
          )}
          <div className="flex justify-between text-xs text-gray-500 my-1">
            <span>{t('covers.close')}</span>
            <span>{t('covers.open')}</span>
          </div>
        </div>

        <div className={cn(isGrid ? "flex mt-2" : "w-full flex mt-2")}>
          <p className="text-gray-500 text-xs">
            {formatTimestamp(cover.timestamp)}
          </p>
          <div className={cn(isGrid ? "shrink-0 flex flex-col items-end gap-0.5" : "shrink-0 flex flex-row items-end gap-0.5")}>
            <span className="text-xs whitespace-nowrap bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full">
              {cover.current_operation ? t(`covers.${cover.current_operation}`) : t('covers.idle')} ({cover.position ?? 0}%)
            </span>
            {isVenetian && <span className="text-xs whitespace-nowrap bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full">
              {t('covers.tilt')} ({cover.tilt}%)
            </span>}
          </div>
        </div>
      </div>
    </div>
  );
});

export default CoverItem;

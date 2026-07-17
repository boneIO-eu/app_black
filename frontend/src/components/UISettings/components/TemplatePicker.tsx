/**
 * TemplatePicker - Dialog for selecting template platform type.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface TemplatePickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (platform: string) => void;
}

/** Platform option definition. */
interface PlatformOption {
  id: string;
  icon: string;
  titleKey: string;
  hintKey: string;
}

const PLATFORMS: PlatformOption[] = [
  { id: 'thermostat', icon: '🌡️', titleKey: 'template.platform_thermostat', hintKey: 'template.platform_thermostat_hint' },
  { id: 'alarm_control_panel', icon: '🚨', titleKey: 'template.platform_alarm_control_panel', hintKey: 'template.platform_alarm_hint' },
  { id: 'gate_cover', icon: '🚪', titleKey: 'template.platform_gate_cover', hintKey: 'template.platform_gate_cover_hint' },
  { id: 'irrigation', icon: '💧', titleKey: 'template.platform_irrigation', hintKey: 'template.platform_irrigation_hint' },
];

/**
 * Dialog with platform selection buttons for creating new template entities.
 */
const TemplatePicker: React.FC<TemplatePickerProps> = ({ open, onOpenChange, onSelect }) => {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-base-100">
        <DialogHeader>
          <DialogTitle>{t('template.select_platform_title')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-4">
          {PLATFORMS.map((platform) => (
            <button
              key={platform.id}
              type="button"
              className="w-full p-4 rounded-lg border border-base-300 hover:border-primary hover:bg-primary/5 transition-colors text-left flex items-start gap-3"
              onClick={() => onSelect(platform.id)}
            >
              <span className="text-2xl">{platform.icon}</span>
              <div>
                <div className="font-semibold">{t(platform.titleKey)}</div>
                <div className="text-sm text-base-content/60">{t(platform.hintKey)}</div>
              </div>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default TemplatePicker;

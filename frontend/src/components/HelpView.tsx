import { useState, useCallback } from 'react';
import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '../hooks/useTranslation';
import {
  FaDiscord,
  FaGithub,
  FaBook,
  FaComments,
  FaServer,
  FaLightbulb,
  FaHome,
} from 'react-icons/fa';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from '@/components/ui/dialog';

/** A single help link definition. */
interface HelpLink {
  icon: React.ReactNode;
  label: string;
  description: string;
  url: string;
  color: string;
}

/**
 * Help content — reusable card grid with resource links.
 * Rendered inside a dialog (mobile: bottom sheet, desktop: centered modal).
 */
function HelpContent({ version }: { version: string }) {
  const { t } = useTranslation();

  const links: HelpLink[] = [
    {
      icon: <FaDiscord className="w-5 h-5" />,
      label: 'Discord',
      description: t('help.discord_community'),
      url: 'https://discord.gg/Hm2CzSjvtu',
      color: 'bg-indigo-500/10 text-indigo-500',
    },
    {
      icon: <FaComments className="w-5 h-5" />,
      label: 'Forum',
      description: t('help.forum_community'),
      url: 'https://forum.boneio.eu',
      color: 'bg-blue-500/10 text-blue-500',
    },
    {
      icon: <FaBook className="w-5 h-5" />,
      label: t('help.documentation'),
      description: 'boneio.eu/docs/black',
      url: 'https://boneio.eu/docs/black',
      color: 'bg-emerald-500/10 text-emerald-500',
    },
    {
      icon: <FaGithub className="w-5 h-5" />,
      label: t('help.app_repository'),
      description: 'boneIO-eu/app_black',
      url: 'https://github.com/boneIO-eu/app_black',
      color: 'bg-gray-500/10 text-gray-400',
    },
    {
      icon: <FaServer className="w-5 h-5" />,
      label: t('help.system_image'),
      description: 'boneIO-eu/black_debian_images',
      url: 'https://github.com/boneIO-eu/black_debian_images',
      color: 'bg-orange-500/10 text-orange-500',
    },
    {
      icon: <FaHome className="w-5 h-5" />,
      label: t('help.ha_dashboard'),
      description: t('help.ha_dashboard_description'),
      url: 'https://github.com/boneIO-eu/home-assistant-addons/tree/main/boneio-dashboard',
      color: 'bg-cyan-500/10 text-cyan-500',
    },
  ];

  return (
    <div className="space-y-5 pr-1 max-h-[70vh] sm:max-h-[65vh] overflow-y-auto">
      {/* Version badge */}
      {version && (
        <div className="flex justify-center">
          <span className="gap-1 badge-outline text-base-content/50 badge badge-sm">
            {t('help.version')}: {version}
          </span>
        </div>
      )}

      {/* Encouraging banner */}
      <div className="bg-linear-to-br from-primary/10 to-secondary/10 p-4 border border-primary/20 rounded-xl">
        <div className="flex items-start gap-3">
          <div className="flex justify-center items-center bg-primary/20 rounded-lg w-8 h-8 shrink-0">
            <FaLightbulb className="w-4 h-4 text-primary" />
          </div>
          <p className="text-sm text-base-content/70 leading-relaxed">
            {t('help.encouraging_text')}
          </p>
        </div>
      </div>

      {/* Resource cards */}
      <div className="gap-2 grid">
        {links.map((link) => (
          <a
            key={link.url}
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex items-center gap-3 bg-base-200/30 hover:bg-base-200/60 p-3 border border-base-300 hover:border-primary/30 rounded-xl transition-all duration-200"
          >
            <div className={`shrink-0 w-10 h-10 rounded-xl ${link.color} flex items-center justify-center transition-transform duration-200 group-hover:scale-110`}>
              {link.icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-sm text-base-content/90 truncate">
                {link.label}
              </p>
              <p className="text-xs text-base-content/50">
                {link.description}
              </p>
            </div>
            <svg className="w-4 h-4 group-hover:text-primary/60 text-base-content/30 transition-colors shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        ))}
      </div>

      {/* Suggestions banner */}
      <div className="bg-success/10 p-4 border border-success/20 rounded-xl">
        <div className="flex items-start gap-3">
          <div className="flex justify-center items-center bg-success/20 rounded-lg w-8 h-8 shrink-0">
            <svg className="w-4 h-4 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="font-semibold text-success text-sm">{t('help.suggestions_title')}</p>
            <p className="mt-0.5 text-xs text-base-content/50 leading-relaxed">
              {t('help.suggestions_text')}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * HelpDialog — Opens help as a dialog.
 * On mobile: slides up as a bottom sheet.
 * On desktop: centered modal.
 *
 * Used from Navigation bar as a trigger button.
 */
export function HelpDialog({ trigger }: { trigger: React.ReactNode }) {
  const { data: initData } = useAppInit();
  const version = initData?.version || '';

  const { t } = useTranslation();

  return (
    <Dialog>
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent maxWidthClass="sm:max-w-2xl" showCloseButton>
        <DialogHeader>
          <DialogTitle>{t('help.title')}</DialogTitle>
          <DialogDescription>{t('help.description')}</DialogDescription>
        </DialogHeader>
        <HelpContent version={version} />
      </DialogContent>
    </Dialog>
  );
}

/**
 * HelpView — Full-page help view (used as a route /help).
 * Wraps HelpContent in a centered container.
 */
export default function HelpView() {
  const { t } = useTranslation();
  const { data: initData } = useAppInit();
  const version = initData?.version || '';
  const [dialogOpen, setDialogOpen] = useState(true);

  const handleOpenChange = useCallback((open: boolean) => {
    setDialogOpen(open);
    if (!open) {
      // Navigate back when dialog closes
      window.history.back();
    }
  }, []);

  return (
    <Dialog open={dialogOpen} onOpenChange={handleOpenChange}>
      <DialogContent maxWidthClass="sm:max-w-2xl" showCloseButton>
        <DialogHeader>
          <DialogTitle>{t('help.title')}</DialogTitle>
          <DialogDescription>{t('help.description')}</DialogDescription>
        </DialogHeader>
        <HelpContent version={version} />
      </DialogContent>
    </Dialog>
  );
}

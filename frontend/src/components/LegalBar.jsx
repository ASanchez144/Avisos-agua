import { Phone } from 'lucide-react';

export const LEGAL_TEXT = 'Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil.';

/** Aviso legal permanente y siempre visible. */
export default function LegalBar({ text = LEGAL_TEXT }) {
  return (
    <footer role="contentinfo" className="flex items-center gap-2 border-t border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-amber-200 sm:text-sm">
      <Phone aria-hidden="true" className="h-4 w-4 shrink-0" />
      <span>{text}</span>
    </footer>
  );
}

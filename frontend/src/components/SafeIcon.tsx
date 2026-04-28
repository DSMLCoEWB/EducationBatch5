import React, { memo, Component, ErrorInfo, ReactNode } from 'react';
import * as LucideIcons from 'lucide-react';
import { Hash } from 'lucide-react';

// REFINED FILTER: Broadly allow PascalCase keys for icons
export const ALL_ICON_NAMES = Object.keys(LucideIcons).filter(
  (name) => /^[A-Z]/.test(name) && !['LucideProps', 'LucideIcon', 'createLucideIcon'].includes(name)
).sort();

// Class-based Error Boundary for total stability
class IconErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { hasError: boolean }> {
  constructor(props: any) { super(props); this.state = { hasError: false }; }
  static getDerivedStateFromError(_: Error) { return { hasError: true }; }
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("🚫 [IconCrash] Caught broken icon render:", error);
  }
  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}

export const SafeIcon = memo(({ iconName, className, style }: { iconName: string; className?: string; style?: React.CSSProperties }) => {
  let IconComp = (LucideIcons as any)[iconName];
  
  if (!IconComp) {
    // Try case-insensitive fallback
    const lowerName = iconName.toLowerCase().replace(/[^a-z0-9]/g, '');
    const match = ALL_ICON_NAMES.find(n => n.toLowerCase().replace(/[^a-z0-9]/g, '') === lowerName);
    if (match) IconComp = (LucideIcons as any)[match];
  }

  // Final fallback to Hash if still missing
  if (!IconComp) {
    return <Hash className={className} style={style} />;
  }

  return (
    <IconErrorBoundary fallback={<Hash className={className} style={style} />}>
      <IconComp className={className} style={style} />
    </IconErrorBoundary>
  );
});

export function normalizeToHex(colorStr: string): string {
  if (!colorStr) return '#3b82f6';
  if (colorStr.startsWith('#')) return colorStr;
  
  // Handle HSL format from DB
  const hslMatch = colorStr.match(/hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)/);
  if (hslMatch) {
    let h = parseInt(hslMatch[1]), s = parseInt(hslMatch[2]) / 100, l = parseInt(hslMatch[3]) / 100;
    const a = s * Math.min(l, 1 - l);
    const f = (n: number) => {
      const k = (n + h / 30) % 12;
      const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
      return Math.round(255 * color).toString(16).padStart(2, '0');
    };
    return `#${f(0)}${f(8)}${f(4)}`;
  }
  
  // Handle RGB format if any
  const rgbMatch = colorStr.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
  if (rgbMatch) {
    const f = (n: string) => parseInt(n).toString(16).padStart(2, '0');
    return `#${f(rgbMatch[1])}${f(rgbMatch[2])}${f(rgbMatch[3])}`;
  }

  return colorStr;
}

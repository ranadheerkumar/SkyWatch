"use client";

import Image from "next/image";
import tractorSupplyLogo from "../../assets/Tractor-Supply-Logo-SVG.svg";

type TractorSupplyLogoVariant = "auth" | "sidebar" | "drawer" | "header";

type TractorSupplyLogoProps = {
  variant?: TractorSupplyLogoVariant;
  className?: string;
  title?: string;
  subtitle?: string;
  showCopy?: boolean;
};

const VARIANT_DIMENSIONS: Record<TractorSupplyLogoVariant, { width: number; height: number }> = {
  auth: { width: 208, height: 57 },
  sidebar: { width: 160, height: 44 },
  drawer: { width: 140, height: 38 },
  header: { width: 124, height: 34 },
};

export default function TractorSupplyLogo({
  variant = "sidebar",
  className = "",
  title = "",
  subtitle = "Tractor Supply Company",
  showCopy = true,
}: TractorSupplyLogoProps) {
  const dimensions = VARIANT_DIMENSIONS[variant];

  return (
    <div className={`tractor-supply-logo tractor-supply-logo-${variant} ${className}`.trim()}>
      <Image
        src={tractorSupplyLogo}
        alt="Tractor Supply"
        width={dimensions.width}
        height={dimensions.height}
        className="tractor-supply-logo-image"
        priority
      />
      {showCopy ? (
        <div className="tractor-supply-logo-copy">
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </div>
      ) : null}
    </div>
  );
}

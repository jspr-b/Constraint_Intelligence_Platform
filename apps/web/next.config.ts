import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const config: NextConfig = {
  transpilePackages: ["@cip/ui"],
  output: "standalone",
  poweredByHeader: false,
};

export default withNextIntl(config);

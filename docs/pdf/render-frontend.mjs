import { renderDocument } from "./render-doc.mjs";

await renderDocument({
  source: "frontend.md",
  outputBase: "firefly-frontend-user-guide",
  title: "Firefly Frontend User Guide",
  headerTitle: "Firefly Frontend User Guide",
  coverLabel: "User Configuration Guide",
  coverTitle: "Firefly Frontend<br />User Guide",
  coverSubtitle:
    "Operational guide for configuring, monitoring, testing, and diagnosing Firefly controller fleets through the web frontend.",
  contextLabel: "Guide scope",
  contextMetadataKey: "Guide scope",
});

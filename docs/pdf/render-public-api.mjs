import { renderDocument } from "./render-doc.mjs";

await renderDocument({
  source: "public-api.md",
  outputBase: "firefly-public-api",
  title: "Firefly Public API Integration Guide",
  headerTitle: "Firefly Public API Integration Guide",
  coverLabel: "Customer Integration Reference",
  coverTitle: "Firefly Public API<br />Integration Guide",
  coverSubtitle:
    "HTTP API reference for customer systems integrating with Macrolet Firefly light-guided picking devices.",
  contextLabel: "API namespace",
  contextMetadataKey: "API namespace",
});

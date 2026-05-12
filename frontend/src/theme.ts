import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Firefly accent: amber/gold with green hint, evoking the firefly glow.
const firefly: MantineColorsTuple = [
  "#fff8e1",
  "#ffecb3",
  "#ffe082",
  "#ffd54f",
  "#ffca28",
  "#ffc107",
  "#ffb300",
  "#ffa000",
  "#ff8f00",
  "#ff6f00",
];

export const theme = createTheme({
  primaryColor: "firefly",
  defaultRadius: "md",
  fontFamily:
    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  headings: {
    fontFamily:
      "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    fontWeight: "600",
  },
  colors: {
    firefly,
  },
  cursorType: "pointer",
});

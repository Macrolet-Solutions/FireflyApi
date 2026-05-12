import { Alert, Text } from "@mantine/core";
import { IconRefresh } from "@tabler/icons-react";

interface Props {
  scope: "segments" | "led-states";
}

const MESSAGES: Record<Props["scope"], string> = {
  segments:
    "Segment changes only reach the device on its next registration. After saving, open the device detail page and press Reset to push the new layout.",
  "led-states":
    "LED state catalog changes only reach the device on its next registration. After saving, open the device detail page and press Reset to push the new catalog.",
};

export function ResetRequiredBanner({ scope }: Props) {
  return (
    <Alert
      icon={<IconRefresh size={16} />}
      color="yellow"
      variant="light"
      title="Device reset required"
      mb="md"
    >
      <Text size="sm">{MESSAGES[scope]}</Text>
    </Alert>
  );
}

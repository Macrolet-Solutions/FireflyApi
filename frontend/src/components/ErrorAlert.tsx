import { Alert } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { isApiError } from "@/api/client";

interface Props {
  error: unknown;
  title?: string;
}

export function ErrorAlert({ error, title = "Something went wrong" }: Props) {
  if (!error) return null;
  let body = "An unknown error occurred.";
  let code: string | undefined;
  if (isApiError(error)) {
    body = error.description;
    code = error.errorCode;
  } else if (error instanceof Error) {
    body = error.message;
  }
  return (
    <Alert
      icon={<IconAlertTriangle size={16} />}
      color="red"
      variant="light"
      title={code ? `${title} (${code})` : title}
      mb="md"
    >
      {body}
    </Alert>
  );
}

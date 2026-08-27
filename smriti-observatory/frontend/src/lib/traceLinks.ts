export function cloudTraceUrl(traceId: string, gcpProject: string): string {
  return `https://console.cloud.google.com/traces/list?tid=${traceId}&project=${gcpProject}`;
}

export function adkWebUrl(tutorBaseUrl: string): string {
  return `${tutorBaseUrl.replace(/\/$/, "")}/dev-ui/`;
}

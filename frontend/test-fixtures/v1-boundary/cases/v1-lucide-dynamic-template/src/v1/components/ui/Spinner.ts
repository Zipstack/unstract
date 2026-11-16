export const loadSpinner = () =>
  import(`lucide-react` as string).then((m) => m.Loader2);

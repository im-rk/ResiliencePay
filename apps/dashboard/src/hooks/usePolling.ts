import { useQuery, UseQueryOptions } from "@tanstack/react-query";

export function usePolling<T>(
  queryKey: readonly unknown[],
  fetchFn: () => Promise<T>,
  intervalMs = 7000,
  options?: Partial<UseQueryOptions<T>>
) {
  return useQuery({
    queryKey,
    queryFn: fetchFn,
    refetchInterval: intervalMs,
    retry: 2, // React Query's built-in retry — handles a single transient network blip transparently
    ...options,
  });
}

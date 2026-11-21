import { addNetworkStateListener } from 'expo-network';
import { useEffect, useRef } from 'react';

/**
 * Runs `callback` when connectivity returns after being lost. The callback is
 * invoked from the network listener (an external event), so refreshing state
 * from it is safe.
 */
export function useOnReconnect(callback: () => void): void {
  const latest = useRef(callback);

  useEffect(() => {
    latest.current = callback;
  }, [callback]);

  useEffect(() => {
    // Unknown initial state: an immediate "connected" event would refresh a
    // consumer whose load is still in progress, which is harmless (it is a
    // no-op while not marked offline) but misses cold-start offline.
    let online = false;

    const subscription = addNetworkStateListener((state) => {
      const next = state.isConnected !== false && state.isInternetReachable !== false;

      if (next && !online) latest.current();
      online = next;
    });

    return () => subscription.remove();
  }, []);
}

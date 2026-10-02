type ToastListener = (message: string) => void;

const listeners = new Set<ToastListener>();

export function showToast(message: string): void {
  listeners.forEach((listener) => {
    try {
      listener(message);
    } catch (err) {
      console.error('Error executing toast listener', err);
    }
  });
}

export function subscribeToast(listener: ToastListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

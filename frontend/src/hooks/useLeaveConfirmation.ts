import { useEffect } from 'react';

interface LeaveConfirmationOptions {
  hasRunningTask?: boolean;
  hasUnsavedChanges?: boolean;
}

export function useLeaveConfirmation({
  hasRunningTask = false,
  hasUnsavedChanges = false,
}: LeaveConfirmationOptions): void {
  const shouldConfirm = hasRunningTask || hasUnsavedChanges;

  useEffect(() => {
    if (!shouldConfirm) {
      return undefined;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [shouldConfirm]);
}

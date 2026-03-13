const STORAGE_KEY = "user-flow-execution-context";

export const saveExecutionContext = (payload) => {
  try {
    const context = {
      ...payload,
      saved_at: new Date().toISOString(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(context));
  } catch {
    // ignore storage errors
  }
};

export const readExecutionContext = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

export const clearExecutionContext = () => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore storage errors
  }
};

import { Dispatch, SetStateAction, useCallback, useEffect, useState } from "react";

declare global {
  interface WindowEventMap {
    "local-storage-update": CustomEvent<string>;
  }
}

function getStorageValue<T>(key: string, defaultValue: T): T {
  if (typeof window === "undefined") return defaultValue; // for nextjs serverside render
  const saved = localStorage.getItem(key);
  if (!saved) return defaultValue;
  const initial = JSON.parse(saved);
  return initial ?? defaultValue;
}

export default function useLocalStorage<T>(key: string, defaultValue: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    return getStorageValue(key, defaultValue);
  });

  useEffect(() => {
    function handleStorageChange(event: CustomEvent) {
      if (event.detail === key) {
        setValue(getStorageValue(key, defaultValue));
      }
    }

    window.addEventListener("local-storage-update", handleStorageChange);
    return () => {
      window.removeEventListener("local-storage-update", handleStorageChange);
    };
  }, [key, value, defaultValue]);

  function updateValue(newValue: T | ((val: T) => T)) {
    const valueToStore = newValue instanceof Function ? newValue(value) : newValue;
    setValue(valueToStore);
    if (typeof window !== "undefined") {
      localStorage.setItem(key, JSON.stringify(valueToStore));
      window.dispatchEvent(new CustomEvent("local-storage-update", { detail: key }));
    }
  }

  return [value, updateValue];
}

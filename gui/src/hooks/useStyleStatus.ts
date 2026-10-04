import { useState, useEffect } from "react";
import { api } from "../backend/api";
import type { StyleStatus } from "../data/types";

export function useStyleStatus() {
  const [styleStatus, setStyleStatus] = useState<StyleStatus | null>(null);
  
  useEffect(() => {
    let live = true;
    void api.styleStatus().then((r) => { 
      if (live) setStyleStatus(r.ok ? r : null); 
    });
    return () => { live = false; };
  }, []);
  
  return styleStatus;
}
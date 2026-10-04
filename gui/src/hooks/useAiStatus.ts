import { useState, useEffect } from "react";
import { api } from "../backend/api";

export function useAiStatus() {
  const [aiReady, setAiReady] = useState(false);
  
  useEffect(() => {
    void api.aiStatus().then((r) => {
      if (r.ok && r.hasKey) {
        setAiReady(true);
      }
    });
  }, []);
  
  return aiReady;
}
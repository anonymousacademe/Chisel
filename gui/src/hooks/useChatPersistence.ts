import { useEffect, useRef, useState } from "react";
import { api } from "../backend/api";
import type { ChatMessage } from "../data/types";
import type { Attachment } from "../data/chat";
import { keptMessages } from "../data/appLogic";

/**
 * A conversation is saved (.assistant/chats/) after every answer, as the panel shows it.
 * Client-driven: callers call `setPersist(true)` after a completed turn (or an attachment
 * change on a saved chat); the next messages/scope/attachments change is then saved. Errors are never stored.
 */
export function useChatPersistence(messages: ChatMessage[], scope: "scene" | "project", attachments: Attachment[]) {
  const chatIdRef = useRef<string | null>(null);   // the saved conversation behind the messages, if any
  const [chatId, setChatId] = useState<string | null>(null);   // (the same, for rendering)
  const setChat = (id: string | null) => { chatIdRef.current = id; setChatId(id); };
  const persistChat = useRef(false);               // set after a completed turn: the next messages change is saved
  useEffect(() => {
    if (!persistChat.current) return;
    persistChat.current = false;
    const kept = keptMessages(messages);
    if (!kept.length) return;
    void api.saveChat(chatIdRef.current, kept, scope, attachments.map(({ kind, id }) => ({ kind, id })))
      .then((r) => { if (r.ok) { chatIdRef.current = r.id; setChatId(r.id); } });
  }, [messages, scope, attachments]);
  /** Ask for the next messages/scope/attachments change to be saved (false: skip it). */
  const setPersist = (on: boolean) => { persistChat.current = on; };
  return { chatIdRef, chatId, setChat, setPersist };
}

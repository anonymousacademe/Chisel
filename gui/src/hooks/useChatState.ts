import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api } from "../backend/api";
import type { ChatMessage, ChatSummary } from "../data/types";
import type { Dialog } from "../data/dialog";
import { attachKey, restoreAttachments, savedToMessages, type Attachment } from "../data/chat";
import type { AssistantTab } from "../components/Assistant";
import type { Notice } from "../components/Toast";
import { useChatPersistence } from "./useChatPersistence";

interface Deps {
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  setDialog: Dispatch<SetStateAction<Dialog>>;
  setTab: (t: AssistantTab) => void;
  setAssistantOpen: (open: boolean) => void;
}

/** The assistant conversation: messages, scope, subject chip, attachments, and the saved-chat list / persistence. */
export function useChatState({ notify, setDialog, setTab, setAssistantOpen }: Deps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [scope, setScope] = useState<"scene" | "project">("scene");
  const [subjectRemoved, setSubjectRemoved] = useState(false);   // the author removed the "About: ..." chip for this chat
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [chatList, setChatList] = useState<ChatSummary[] | null>(null);
  const { chatIdRef, chatId, setChat, setPersist } = useChatPersistence(messages, scope, attachments);

  const newChat = () => {
    setChat(null); setPersist(false);
    setMessages([]); setAttachments([]); setSubjectRemoved(false); setDialog(null);
  };
  const openChatHistory = async () => {
    setChatList(null);
    setDialog({ kind: "chats" });
    const r = await api.listChats();
    if (r.ok) setChatList(r.chats); else notify(r.error, "error");
  };
  const loadChat = async (id: string) => {
    const r = await api.openChat(id);
    if (!r.ok) return notify(r.error, "error");
    const c = r.chat;
    const items = await api.listAttachable();
    const known = new Map((items.ok ? items.items : []).map((i) => [attachKey(i), i]));
    setChat(c.id); setPersist(false);
    setMessages(savedToMessages(c.messages));
    setScope(c.scope); setSubjectRemoved(false);
    const restored = restoreAttachments(c.attachments, known);
    setAttachments(restored.attachments);
    if (restored.missing) notify("Some attachments of this chat no longer exist and were left off.");
    setDialog(null); setTab("assistant"); setAssistantOpen(true);
  };
  const renameChat = async (id: string, title: string) => {
    const r = await api.renameChat(id, title);
    if (!r.ok) { notify(r.error, "error"); return false; }
    setChatList(r.chats);
    return true;
  };
  const deleteChat = async (id: string) => {
    const r = await api.deleteChat(id);
    if (!r.ok) { notify(r.error, "error"); return false; }
    setChatList(r.chats);
    if (chatIdRef.current === id) setChat(null);   // the next answer starts a new saved chat
    return true;
  };
  const openAttach = async () => {
    const r = await api.listAttachable();
    if (!r.ok) return notify(r.error, "error");
    setDialog({ kind: "attach", items: r.items, maxWords: r.maxWords, maxItems: r.maxItems });
  };

  return {
    messages, setMessages, scope, setScope, subjectRemoved, setSubjectRemoved, attachments, setAttachments,
    chatList, chatId, chatIdRef, setPersist, newChat, openChatHistory, loadChat, renameChat, deleteChat, openAttach,
  };
}

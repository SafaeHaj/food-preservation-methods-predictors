"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Send, X, Loader2, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { api, type AssistantChatMessage, type AssistantToolCall } from "@/lib/api";
import { usePredictionStore } from "@/components/prediction-store";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls?: AssistantToolCall[];
  error?: boolean;
}

const SUGGESTIONS = [
  "What is this project about?",
  "Which model performs best?",
  "What does water activity mean?",
  "How does salt content affect shelf life?",
];

function pageContextFor(pathname: string, lastPrediction: ReturnType<typeof usePredictionStore>["lastPrediction"]) {
  const ctx: Record<string, unknown> = { current_page: pathname };
  if (lastPrediction) {
    ctx.last_prediction = {
      model: lastPrediction.control.model,
      control_prediction_days: lastPrediction.control.prediction_days,
      candidates: lastPrediction.candidates.map((c) => ({
        name: c.candidate_name,
        predicted_shelf_life_days: c.predicted_candidate_shelf_life,
        relative_improvement_pct: c.relative_improvement_pct,
      })),
    };
  }
  return ctx;
}

export function AssistantChat() {
  const [open, setOpen] = React.useState(false);
  const [messages, setMessages] = React.useState<DisplayMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const { lastPrediction } = usePredictionStore();

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, loading]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    const nextMessages: DisplayMessage[] = [...messages, { role: "user", content: trimmed }];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);
    try {
      const history: AssistantChatMessage[] = nextMessages.map((m) => ({ role: m.role, content: m.content }));
      const res = await api.assistantChat({
        messages: history,
        page_context: pageContextFor(pathname, lastPrediction),
      });
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply, toolCalls: res.tool_calls }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            err instanceof Error
              ? `I couldn't reach the assistant backend: ${err.message}`
              : "I couldn't reach the assistant backend.",
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.4, duration: 0.3 }}
        className="fixed bottom-6 right-6 z-40"
      >
        <Button
          onClick={() => setOpen((v) => !v)}
          size="icon"
          className="h-13 w-13 rounded-full shadow-lg"
          aria-label={open ? "Close AI assistant" : "Open AI assistant"}
        >
          <AnimatePresence mode="wait" initial={false}>
            {open ? (
              <motion.span key="close" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.15 }}>
                <X className="h-5 w-5" />
              </motion.span>
            ) : (
              <motion.span key="sparkle" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }} transition={{ duration: 0.15 }}>
                <Sparkles className="h-5 w-5" />
              </motion.span>
            )}
          </AnimatePresence>
        </Button>
      </motion.div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.97 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="fixed bottom-24 right-6 z-40 flex h-[min(640px,calc(100vh-8rem))] w-[min(400px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-xl border bg-popover shadow-lg"
          >
            <div className="flex shrink-0 items-center gap-2.5 border-b bg-secondary/40 px-4 py-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-foreground">Ask AI</p>
                <p className="truncate text-[11px] text-muted-foreground">Shelf-Life Studio assistant, local &amp; private</p>
              </div>
            </div>

            <ScrollArea className="min-h-0 flex-1 px-4 py-3">
              {messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-4 py-8 text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                    <Sparkles className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">How can I help?</p>
                    <p className="mx-auto mt-1 max-w-[26ch] text-xs text-muted-foreground">
                      Ask about the dataset, models, predictions, or general food-science background.
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-center gap-1.5">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        className="rounded-full border bg-secondary/50 px-2.5 py-1 text-[11px] text-secondary-foreground transition-colors hover:bg-secondary"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {messages.map((m, i) => (
                    <ChatBubble key={i} message={m} />
                  ))}
                  {loading && (
                    <div className="flex items-center gap-2 self-start rounded-lg bg-secondary px-3 py-2 text-xs text-muted-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Thinking…
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>
              )}
            </ScrollArea>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="flex shrink-0 items-end gap-2 border-t p-3"
            >
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                placeholder="Ask a question…"
                rows={1}
                className="max-h-24 min-h-9 resize-none py-2 text-sm"
              />
              <Button type="submit" size="icon" disabled={loading || !input.trim()} className="shrink-0">
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function ChatBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex flex-col gap-1", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : message.error
              ? "border border-destructive/30 bg-destructive/10 text-destructive"
              : "bg-secondary text-secondary-foreground",
        )}
      >
        {message.content}
      </div>
      {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
        <div className="flex flex-wrap gap-1 px-1">
          {message.toolCalls.map((tc, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-[10px] text-muted-foreground"
              title={JSON.stringify(tc.arguments)}
            >
              <Wrench className="h-2.5 w-2.5" />
              {tc.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

import { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Bot } from 'lucide-react';
import { Email } from '@/types';
import { askChatbot } from '@/services/api';

interface ChatbotProps {
  emails: Email[];
}

interface Message {
  id: string;
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
}

export function Chatbot({ emails }: ChatbotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'bot',
      content: 'Hello! I can help you query the grievance email database. Ask me questions like:\n\n• "How many suspension emails in the last 7 days?"\n• "Show follow-up emails from XYZ College"\n• "How many emails had attachments?"',
      timestamp: new Date()
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const processQuery = async (query: string): Promise<string> => {
    try {
      return await askChatbot(query);
    } catch (error) {
      console.error('Chatbot API error, using fallback:', error);
      return processFallbackQuery(query);
    }
  };

  const processFallbackQuery = (query: string): string => {
    const lowerQuery = query.toLowerCase();

    if (lowerQuery.includes('suspension') && (lowerQuery.includes('how many') || lowerQuery.includes('count'))) {
      const days = lowerQuery.match(/(\d+)\s*days?/)?.[1];
      let filtered = emails.filter(e => e.category === 'suspension');
      if (days) {
        const daysAgo = new Date();
        daysAgo.setDate(daysAgo.getDate() - parseInt(days));
        filtered = filtered.filter(e => new Date(e.emailDate) >= daysAgo);
      }
      return `${filtered.length} suspension email${filtered.length !== 1 ? 's' : ''}${days ? ` in the last ${days} days` : ''}.`;
    }

    if (lowerQuery.includes('fir') && (lowerQuery.includes('how many') || lowerQuery.includes('count'))) {
      const days = lowerQuery.match(/(\d+)\s*days?/)?.[1];
      let filtered = emails.filter(e => e.category === 'fir');
      if (days) {
        const daysAgo = new Date();
        daysAgo.setDate(daysAgo.getDate() - parseInt(days));
        filtered = filtered.filter(e => new Date(e.emailDate) >= daysAgo);
      }
      return `${filtered.length} FIR/arrest email${filtered.length !== 1 ? 's' : ''}${days ? ` in the last ${days} days` : ''}.`;
    }

    if (lowerQuery.includes('attachment') && (lowerQuery.includes('how many') || lowerQuery.includes('count'))) {
      const withAttachments = emails.filter(e => e.hasAttachment);
      return `${withAttachments.length} email${withAttachments.length !== 1 ? 's' : ''} with attachments.`;
    }

    if (lowerQuery.includes('follow') && lowerQuery.includes('up')) {
      const followUps = emails.filter(e => e.mailType === 'follow-up');
      const collegeMatch = lowerQuery.match(/from\s+([a-z\s]+)/i);
      if (collegeMatch) {
        const collegeName = collegeMatch[1].trim();
        const collegeFollowUps = followUps.filter(e => e.instituteName.toLowerCase().includes(collegeName));
        if (collegeFollowUps.length === 0) return `No follow-up emails found from "${collegeName}".`;
        const list = collegeFollowUps.slice(0, 5).map(e => `• ${e.subject} (${new Date(e.emailDate).toLocaleDateString()})`).join('\n');
        return `Found ${collegeFollowUps.length} follow-up email${collegeFollowUps.length !== 1 ? 's' : ''} from "${collegeName}":\n\n${list}${collegeFollowUps.length > 5 ? '\n\n...and more' : ''}`;
      }
      return `${followUps.length} follow-up email${followUps.length !== 1 ? 's' : ''}.`;
    }

    if ((lowerQuery.includes('total') || lowerQuery.includes('how many')) && lowerQuery.includes('email')) {
      return `${emails.length} total email${emails.length !== 1 ? 's' : ''}.`;
    }

    return "I'm not sure how to answer that. Try:\n\n• \"How many suspension emails?\"\n• \"Show follow-up emails from [College]\"\n• \"Count emails with attachments\"";
  };

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    const query = inputValue;
    setInputValue('');
    setIsLoading(true);

    try {
      const answer = await processQuery(query);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'bot',
        content: answer,
        timestamp: new Date()
      }]);
    } catch {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'bot',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {/* Floating button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 w-12 h-12 bg-primary text-primary-foreground rounded-full shadow-elevated hover:shadow-modal transition-all flex items-center justify-center z-40 hover:scale-105 active:scale-95"
          aria-label="Open chat assistant"
        >
          <MessageCircle className="w-5 h-5" />
        </button>
      )}

      {/* Chat panel */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 w-[380px] h-[560px] bg-card rounded-xl shadow-modal z-40 flex flex-col border border-border animate-scale-in overflow-hidden">
          {/* Header */}
          <div className="bg-primary text-primary-foreground px-4 py-3 flex items-center justify-between rounded-t-xl">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4" />
              <h3 className="font-semibold text-sm">AI Assistant</h3>
            </div>
            <button onClick={() => setIsOpen(false)} className="p-1 hover:bg-primary-foreground/10 rounded transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
            {messages.map((message) => (
              <div key={message.id} className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-xl px-3.5 py-2.5 ${
                  message.type === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                }`}>
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
                  <p className={`text-[10px] mt-1 ${message.type === 'user' ? 'text-primary-foreground/60' : 'text-muted-foreground'}`}>
                    {message.timestamp.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-muted rounded-xl px-4 py-3">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-muted-foreground/40 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border p-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder="Ask a question..."
                className="flex-1 px-3 py-2 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring/30 placeholder:text-muted-foreground"
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !inputValue.trim()}
                className="px-3 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

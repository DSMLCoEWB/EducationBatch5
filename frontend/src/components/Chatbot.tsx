import { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Bot, Maximize2, Minimize2, Sparkles, Database, FileText } from 'lucide-react';
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
  sources?: { section: string; text: string }[];
}

export function Chatbot({ }: ChatbotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'bot',
      content: 'Hello! I am your **AI Education Assistant**. I can help you with:\n\n*   **Policy Queries**: "How do I handle student suspension?"\n*   **Data Analysis**: "How many pending grievances in Pune?"\n*   **Status Updates**: "Show latest follow-ups from Shivaji College."',
      timestamp: new Date()
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

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
      const answer = await askChatbot(query);
      
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'bot',
        content: answer || "I'm sorry, I couldn't process that. Please try rephrasing.",
        timestamp: new Date()
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'bot',
        content: 'Failed to connect to AI engine. Please ensure the backend is running.',
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const formatMessage = (content: string) => {
    // Simple pseudo-markdown to HTML for 'Premium' feel without dependencies
    return content
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br/>')
      .replace(/•\s?(.*?)(?=<br\/>|$)/g, '<li class="ml-4">$1</li>');
  };

  return (
    <>
      {/* Floating Sparkle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 group flex items-center gap-2 sm:gap-3 gradient-primary text-primary-foreground pl-3 sm:pl-4 pr-4 sm:pr-5 py-2.5 sm:py-3 rounded-full shadow-glow transition-all z-40 hover:opacity-90 hover:scale-105 active:scale-95 animate-in fade-in zoom-in duration-300"
        >
          <div className="relative">
            <Sparkles className="w-5 h-5 animate-pulse" />
            <div className="absolute inset-0 bg-white/20 rounded-full animate-ping scale-150" />
          </div>
          <span className="font-semibold text-sm tracking-tight">AI Assistant</span>
        </button>
      )}

      {/* Modern Glassmorphic Chat Panel */}
      {isOpen && (
        <div 
          className={`fixed bottom-4 right-4 sm:bottom-6 sm:right-6 ${
            isExpanded ? 'w-[calc(100vw-2rem)] sm:w-[800px] h-[80vh]' : 'w-[calc(100vw-2rem)] sm:w-[420px] h-[70vh] sm:h-[600px]'
          } bg-card/80 backdrop-blur-xl rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] z-50 flex flex-col border border-white/20 transition-all duration-500 ease-out animate-in slide-in-from-bottom-10`}
        >
          {/* Header */}
          <div className="p-4 flex items-center justify-between border-b border-white/10 bg-gradient-to-r from-primary/10 to-transparent rounded-t-2xl">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center border border-primary/30">
                <Bot className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-bold text-sm tracking-tight text-foreground">AICOE Intelligent Assistant</h3>
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">Active reasoning</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button 
                onClick={() => setIsExpanded(!isExpanded)} 
                className="p-1.5 hover:bg-white/10 rounded-lg transition-colors text-muted-foreground"
                title={isExpanded ? "Minimize" : "Expand"}
              >
                {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </button>
              <button onClick={() => setIsOpen(false)} className="p-1.5 hover:bg-gov-red/10 hover:text-gov-red rounded-lg transition-colors text-muted-foreground">
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-5 space-y-6 custom-scrollbar scroll-smooth">
            {messages.map((message) => (
              <div key={message.id} className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex gap-3 max-w-[85%] ${message.type === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-[10px] font-bold ${
                    message.type === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted border border-border'
                  }`}>
                    {message.type === 'user' ? 'YOU' : <Bot className="w-4 h-4" />}
                  </div>
                  <div className="space-y-1">
                    <div className={`rounded-2xl px-4 py-3 shadow-sm ${
                      message.type === 'user'
                        ? 'bg-primary text-primary-foreground rounded-tr-none'
                        : 'bg-background dark:bg-muted border border-border rounded-tl-none'
                    }`}>
                      <div 
                        className={`text-sm leading-relaxed prose prose-sm max-w-none ${
                          message.type === 'user' 
                            ? 'prose-invert text-primary-foreground' 
                            : 'dark:prose-invert text-foreground'
                        } prose-headings:text-primary`}
                        dangerouslySetInnerHTML={{ __html: formatMessage(message.content) }}
                      />
                    </div>
                    <span className={`text-[10px] font-medium opacity-50 px-1 block ${message.type === 'user' ? 'text-right' : 'text-left'}`}>
                      {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="flex justify-start">
                <div className="flex gap-3 max-w-[85%]">
                  <div className="w-7 h-7 rounded-full bg-muted border border-border flex items-center justify-center">
                    <Bot className="w-4 h-4 animate-bounce" />
                  </div>
                  <div className="bg-background border border-border rounded-2xl rounded-tl-none px-4 py-3 shadow-sm">
                    <div className="flex gap-1.5 py-1">
                      <div className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <div className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <div className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce" />
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="p-4 bg-gradient-to-t from-background to-transparent">
            <div className="relative group">
              <div className="absolute -inset-0.5 bg-gradient-to-r from-primary/50 to-primary/20 rounded-xl blur opacity-30 group-focus-within:opacity-100 transition duration-500"></div>
              <div className="relative flex items-center bg-background border border-border rounded-xl px-3 py-2 shadow-inner">
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  placeholder="Query policy manual or database..."
                  className="flex-1 bg-transparent px-2 py-1.5 text-sm focus:outline-none placeholder:text-muted-foreground/50"
                />
                <button
                  onClick={handleSend}
                  disabled={isLoading || !inputValue.trim()}
                  className="p-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-all disabled:opacity-30 disabled:grayscale transform active:scale-95 shadow-lg shadow-primary/20"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            {/* Quick Actions Footer */}
            <div className="flex gap-2 mt-3 overflow-x-auto pb-1 no-scrollbar">
               {[
                 { label: 'Policy Check', icon: FileText },
                 { label: 'Data Stats', icon: Database }
               ].map((action, i) => (
                 <button 
                  key={i}
                  onClick={() => setInputValue(prev => prev + (prev ? ' ' : '') + action.label)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted hover:bg-primary/10 hover:text-primary transition-all text-[10px] font-bold whitespace-nowrap border border-border group"
                 >
                   <action.icon className="w-3 h-3 text-muted-foreground group-hover:text-primary" />
                   {action.label}
                 </button>
               ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

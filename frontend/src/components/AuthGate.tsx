import { useState, useEffect, useCallback } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { KeyRound } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { setStoredApiKey, clearStoredApiKey, getStoredApiKey } from '../services/api/base';

/**
 * Trimmed before validation and storage so stray whitespace never reaches
 * the Authorization header. Platform keys look like `pk_...` but the format
 * is not enforced client-side (the backend is the authority on validity).
 */
const authGateSchema = z.object({
  apiKey: z.string().trim().min(1, 'Please enter an API key'),
});

type AuthGateValues = z.infer<typeof authGateSchema>;

/**
 * AuthGate wraps the app and listens for auth:unauthorized events.
 * When a 401 is received, it shows a modal dialog prompting the user
 * to enter a platform API key. The key is stored in localStorage and
 * injected into all subsequent API requests.
 *
 * In bootstrap mode (no API keys created yet), no 401s occur and
 * this component stays invisible.
 */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [showPrompt, setShowPrompt] = useState(false);

  const form = useForm<AuthGateValues>({
    resolver: zodResolver(authGateSchema),
    defaultValues: { apiKey: '' },
  });

  const handleUnauthorized = useCallback(() => {
    setShowPrompt(true);
    // Clear any stale validation error from a previous prompt; keep the
    // typed value (matches pre-RHF behavior).
    form.clearErrors();
  }, [form]);

  useEffect(() => {
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, [handleUnauthorized]);

  const handleConnect = (values: AuthGateValues) => {
    // values.apiKey is already trimmed by the schema.
    setStoredApiKey(values.apiKey);
    setShowPrompt(false);
    form.reset();
    // Reload the page to retry all failed requests with the new key
    window.location.reload();
  };

  const handleDisconnect = () => {
    clearStoredApiKey();
    form.reset();
    window.location.reload();
  };

  const hasStoredKey = getStoredApiKey() !== null;

  return (
    <>
      {children}
      <Dialog open={showPrompt} onOpenChange={setShowPrompt}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5" />
              API Key Required
            </DialogTitle>
            <DialogDescription asChild>
              <div className="space-y-2">
                <p>
                  {hasStoredKey
                    ? 'Your stored API key is invalid or expired. Please enter a new one.'
                    : 'Enter a platform API key to access Agentbase.'}
                </p>
                <p className="text-xs text-muted-foreground">
                  An administrator can create API keys from the local Agentbase instance
                  by navigating to the API Keys page on the LAN.
                </p>
              </div>
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            {/* space-y-4 stands in for DialogContent's grid gap-4 now that the
                field block and footer share a single <form> child. */}
            <form onSubmit={form.handleSubmit(handleConnect)} className="space-y-4">
              <div className="space-y-3 py-2">
                <FormField
                  control={form.control}
                  name="apiKey"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>API Key</FormLabel>
                      <FormControl>
                        <Input
                          type="password"
                          placeholder="pk_..."
                          autoFocus
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <DialogFooter className="flex justify-between sm:justify-between">
                {hasStoredKey && (
                  <Button type="button" variant="outline" onClick={handleDisconnect}>
                    Clear stored key
                  </Button>
                )}
                <Button type="submit">
                  Connect
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </>
  );
}

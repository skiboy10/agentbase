import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { KeyRound, Plus, Trash2, Copy, Check, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageHeader, ErrorBanner, EmptyState } from '@/components';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import { authApi } from '../services/api/auth';
import type { APIKey, APIKeyCreate } from '../services/api/types/auth';

const AVAILABLE_SCOPES = ['read', 'write', 'admin'] as const;

/**
 * Create-key form schema. Name is trimmed before validation/submission;
 * at least one scope must be selected. The Create button is also disabled
 * until these hold (pre-RHF behavior preserved), so the schema acts as the
 * backstop for any submit path (e.g., Enter key).
 */
const createKeySchema = z.object({
  name: z.string().trim().min(1, 'Name is required'),
  scopes: z.array(z.enum(AVAILABLE_SCOPES)).min(1, 'Select at least one scope'),
});

type CreateKeyValues = z.infer<typeof createKeySchema>;

/**
 * Theme-aware scope badge classes using design tokens from the --cat-scope-*
 * family (index.css + tailwind.config.js). No raw palette colors.
 */
const scopeColors: Record<string, string> = {
  read: 'bg-cat-scope-read/15 text-cat-scope-read border-cat-scope-read/30',
  write: 'bg-cat-scope-write/15 text-cat-scope-write border-cat-scope-write/30',
  admin: 'bg-cat-scope-admin/15 text-cat-scope-admin border-cat-scope-admin/30',
};

/**
 * Format a date string for display. Guards against malformed input:
 * if the Date parse yields NaN, returns the raw string rather than throwing.
 */
export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;
  return date.toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function APIKeysPage() {
  const { toast } = useToast();
  const [keys, setKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showKeyDialog, setShowKeyDialog] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [revokeTarget, setRevokeTarget] = useState<APIKey | null>(null);
  const [revokeError, setRevokeError] = useState('');
  const [revoking, setRevoking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showInactive, setShowInactive] = useState(false);

  // Create form state (react-hook-form + zod; see createKeySchema)
  const createForm = useForm<CreateKeyValues>({
    resolver: zodResolver(createKeySchema),
    defaultValues: { name: '', scopes: ['read'] },
  });
  const createName = createForm.watch('name');
  const createScopes = createForm.watch('scopes');
  const creating = createForm.formState.isSubmitting;

  const fetchKeys = async () => {
    try {
      setLoading(true);
      const data = await authApi.listKeys();
      setKeys(data);
      setError('');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load API keys';
      // Don't show auth errors on this page (AuthGate handles it)
      if (msg !== 'Authentication required') {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleCreate = async (values: CreateKeyValues) => {
    try {
      const data: APIKeyCreate = {
        name: values.name, // already trimmed by the schema
        scopes: values.scopes,
      };
      const result = await authApi.createKey(data);
      setNewKey(result.api_key);
      setShowCreateDialog(false);
      setShowKeyDialog(true);
      createForm.reset();
      fetchKeys();
    } catch (e: unknown) {
      // Toast, not the page ErrorBanner — the still-open dialog would hide it.
      toast({
        title: 'Create failed',
        description: e instanceof Error ? e.message : 'Failed to create key',
        variant: 'destructive',
      });
    }
  };

  const handleRevoke = async () => {
    if (!revokeTarget || revoking) return;
    setRevokeError('');
    setRevoking(true);
    try {
      await authApi.revokeKey(revokeTarget.id);
      // Close the dialog only after the API call resolves successfully.
      setRevokeTarget(null);
      fetchKeys();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to revoke key';
      // Surface error inside the open dialog (visible despite the overlay) and
      // as a destructive toast. Dialog stays open so the user can retry.
      setRevokeError(msg);
      toast({ title: 'Revoke failed', description: msg, variant: 'destructive' });
    } finally {
      setRevoking(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(newKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filteredKeys = showInactive ? keys : keys.filter(k => k.is_active);
  const activeCount = keys.filter(k => k.is_active).length;
  const inactiveCount = keys.filter(k => !k.is_active).length;

  return (
    <div className="p-6 h-full overflow-y-auto">
    <div className="space-y-6">
      <PageHeader
        title="API Keys"
        description="Manage platform API keys for programmatic access and MCP connections."
        action={{ label: 'Create Key', icon: <Plus className="h-4 w-4 mr-2" />, onClick: () => setShowCreateDialog(true) }}
      />

      <ErrorBanner error={error} onDismiss={() => setError('')} />

      {/* Summary */}
      <div className="flex gap-4 text-sm text-muted-foreground">
        <span>{activeCount} active</span>
        {inactiveCount > 0 && (
          <button
            className="underline hover:text-foreground"
            onClick={() => setShowInactive(!showInactive)}
          >
            {showInactive ? 'Hide' : 'Show'} {inactiveCount} revoked
          </button>
        )}
      </div>

      {/* Key List */}
      {loading ? (
        <div className="text-center py-12 text-muted-foreground">Loading...</div>
      ) : filteredKeys.length === 0 ? (
        <EmptyState
          icon={<KeyRound className="w-16 h-16" />}
          title="No API keys yet"
          description="Create your first API key to enable authenticated access."
          action={{ label: 'Create Key', onClick: () => setShowCreateDialog(true) }}
        />
      ) : (
        <div className="space-y-3">
          {filteredKeys.map((key) => (
            <Card key={key.id} className={!key.is_active ? 'opacity-60' : ''}>
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <span className="font-medium">{key.name}</span>
                      <code className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                        {key.key_prefix}...
                      </code>
                      {!key.is_active && (
                        <Badge variant="outline" className="text-muted-foreground">
                          Revoked
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <div className="flex gap-1.5">
                        {key.scopes.map(scope => (
                          <Badge key={scope} variant="outline" className={scopeColors[scope] || ''}>
                            {scope}
                          </Badge>
                        ))}
                      </div>
                      <span>Created {formatDate(key.created_at)}</span>
                      {key.last_used_at && (
                        <span>Last used {formatDate(key.last_used_at)}</span>
                      )}
                      {key.expires_at && (
                        <span className="flex items-center gap-1">
                          {new Date(key.expires_at) < new Date() ? (
                            <>
                              <AlertTriangle className="h-3 w-3 text-destructive" />
                              Expired
                            </>
                          ) : (
                            <>Expires {formatDate(key.expires_at)}</>
                          )}
                        </span>
                      )}
                    </div>
                  </div>
                  {key.is_active && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setRevokeTarget(key)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
            <DialogDescription>
              Create a new platform API key with specific permissions.
            </DialogDescription>
          </DialogHeader>
          <Form {...createForm}>
            {/* space-y-4 stands in for DialogContent's grid gap-4 now that the
                field block and footer share a single <form> child. */}
            <form onSubmit={createForm.handleSubmit(handleCreate)} className="space-y-4">
              <div className="space-y-4 py-2">
                <FormField
                  control={createForm.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g., MCP Connection, CI/CD Pipeline"
                          autoFocus
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={createForm.control}
                  name="scopes"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Scopes</FormLabel>
                      <div className="space-y-2">
                        {AVAILABLE_SCOPES.map(scope => (
                          <div key={scope} className="flex items-center gap-2">
                            <Checkbox
                              id={`scope-${scope}`}
                              checked={field.value.includes(scope)}
                              onCheckedChange={(checked) =>
                                field.onChange(
                                  checked === true
                                    ? [...field.value, scope]
                                    : field.value.filter(s => s !== scope)
                                )
                              }
                            />
                            <Label htmlFor={`scope-${scope}`} className="flex items-center gap-2 font-normal cursor-pointer">
                              <Badge variant="outline" className={scopeColors[scope]}>
                                {scope}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {scope === 'read' && '— GET operations, search'}
                                {scope === 'write' && '— Create, update, delete resources'}
                                {scope === 'admin' && '— Key management, system config'}
                              </span>
                            </Label>
                          </div>
                        ))}
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setShowCreateDialog(false)}>
                  Cancel
                </Button>
                {/* Disabled-until-valid preserved from the pre-RHF version; the
                    zod schema backstops any other submit path. */}
                <Button
                  type="submit"
                  disabled={!createName.trim() || createScopes.length === 0 || creating}
                >
                  {creating ? 'Creating...' : 'Create Key'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Key Reveal Dialog */}
      <Dialog open={showKeyDialog} onOpenChange={(open) => {
        setShowKeyDialog(open);
        if (!open) setNewKey('');
      }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>API Key Created</DialogTitle>
            <DialogDescription>
              Copy this key now. It will not be shown again.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-muted p-3 rounded-md text-sm font-mono break-all select-all">
                {newKey}
              </code>
              <Button variant="outline" size="sm" onClick={handleCopy}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <div className="bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-md p-3 text-sm flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>Store this key securely. You will not be able to see it again after closing this dialog.</span>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => { setShowKeyDialog(false); setNewKey(''); }}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke Confirmation */}
      <AlertDialog open={!!revokeTarget} onOpenChange={(open) => { if (!open) { setRevokeTarget(null); setRevokeError(''); } }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API Key</AlertDialogTitle>
            <AlertDialogDescription>
              This will immediately invalidate the key "{revokeTarget?.name}".
              Any integrations using this key will stop working.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {revokeError && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{revokeError}</span>
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revoking}>Cancel</AlertDialogCancel>
            {/* Plain Button instead of AlertDialogAction: AlertDialogAction
                auto-dismisses on click, which would close the dialog before the
                async revoke resolves and hide the inline error on failure. */}
            <Button variant="destructive" onClick={handleRevoke} disabled={revoking}>
              {revoking ? 'Revoking...' : 'Revoke Key'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
    </div>
  );
}

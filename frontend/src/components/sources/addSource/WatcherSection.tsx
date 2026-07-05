import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface WatcherSectionProps {
  watchEnabled: boolean
  setWatchEnabled: (value: boolean) => void
  watchMode: string
  setWatchMode: (value: string) => void
  pollIntervalMinutes: string
  setPollIntervalMinutes: (value: string) => void
  debounceSeconds: string
  setDebounceSeconds: (value: string) => void
  maxFileSizeMb: string
  setMaxFileSizeMb: (value: string) => void
}

export default function WatcherSection({
  watchEnabled,
  setWatchEnabled,
  watchMode,
  setWatchMode,
  pollIntervalMinutes,
  setPollIntervalMinutes,
  debounceSeconds,
  setDebounceSeconds,
  maxFileSizeMb,
  setMaxFileSizeMb,
}: WatcherSectionProps) {
  return (
    <div className="p-3 border rounded-lg space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <Label className="text-sm font-medium">Directory Watcher</Label>
          <p className="text-xs text-muted-foreground">
            Detect file adds, edits, and deletes and re-index only what changed.
            Polls every {pollIntervalMinutes || 5} min when filesystem events
            aren't available.
          </p>
        </div>
        <Switch checked={watchEnabled} onCheckedChange={setWatchEnabled} />
      </div>

      {watchEnabled && (
        <div className="space-y-3 pt-1">
          <div className="space-y-1">
            <Label className="text-xs">Watch Mode</Label>
            <Select value={watchMode} onValueChange={setWatchMode}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Select mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto (detect best method)</SelectItem>
                <SelectItem value="polling">Polling</SelectItem>
                <SelectItem value="events">Events (inotify/FSEvents)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Poll Interval</Label>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min="1"
                  value={pollIntervalMinutes}
                  onChange={(e) => setPollIntervalMinutes(e.target.value)}
                  className="h-8 text-xs"
                />
                <span className="text-xs text-muted-foreground whitespace-nowrap">min</span>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Debounce</Label>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min="1"
                  value={debounceSeconds}
                  onChange={(e) => setDebounceSeconds(e.target.value)}
                  className="h-8 text-xs"
                />
                <span className="text-xs text-muted-foreground whitespace-nowrap">sec</span>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Max File Size</Label>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min="1"
                  value={maxFileSizeMb}
                  onChange={(e) => setMaxFileSizeMb(e.target.value)}
                  className="h-8 text-xs"
                />
                <span className="text-xs text-muted-foreground whitespace-nowrap">MB</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

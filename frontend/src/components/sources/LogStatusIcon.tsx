import { CheckCircle, XCircle, Clock, Activity } from 'lucide-react'
import { statusClasses, sourceStatusVariant } from '../../lib/status'

interface LogStatusIconProps {
  status: string
}

export default function LogStatusIcon({ status }: LogStatusIconProps) {
  switch (status) {
    case 'done':
      return <CheckCircle className={`w-4 h-4 ${statusClasses('success').text}`} />
    case 'failed':
      return <XCircle className={`w-4 h-4 ${statusClasses('error').text}`} />
    case 'scraping':
    case 'embedding':
      return <Activity className={`w-4 h-4 ${statusClasses('warning').text} animate-pulse`} />
    case 'scraped':
      return <Clock className={`w-4 h-4 ${statusClasses('info').text}`} />
    case 'pending':
    default:
      return <Clock className="w-4 h-4 text-muted-foreground" />
  }
}

export function getStatusColor(status: string): string {
  return statusClasses(sourceStatusVariant(status)).text
}

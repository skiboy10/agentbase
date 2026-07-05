import { useState, useEffect } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { Database, Cloud, Settings, ChevronRight, ChevronLeft, Bot, BookOpen, Menu, KeyRound, Tags, Library, Rocket, MessageSquare, Activity, FlaskConical } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../lib/utils'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Separator } from '@/components/ui/separator'
import { useIndexingToasts } from '../hooks/useIndexingToasts'

interface NavItem {
  name: string
  href: string
  icon: LucideIcon
}

interface NavSection {
  label: string
  items: NavItem[]
}

const navigation: NavSection[] = [
  {
    label: 'Knowledge',
    items: [
      { name: 'Sources', href: '/sources', icon: Database },
      { name: 'Automations', href: '/automations', icon: Activity },
      { name: 'Libraries', href: '/libraries', icon: Library },
      { name: 'Taxonomy', href: '/taxonomy', icon: Tags },
    ],
  },
  {
    label: 'Agents',
    items: [
      { name: 'Agents', href: '/agents', icon: Bot },
      { name: 'Prompt Studio', href: '/prompt-studio', icon: MessageSquare },
    ],
  },
  {
    label: 'Lab',
    items: [
      { name: 'Experiments', href: '/experiments', icon: FlaskConical },
    ],
  },
  {
    label: 'Configure',
    items: [
      { name: 'Providers', href: '/providers', icon: Cloud },
      { name: 'Settings', href: '/settings', icon: Settings },
      { name: 'API Keys', href: '/keys', icon: KeyRound },
    ],
  },
  {
    label: 'Reference',
    items: [
      { name: 'Quickstart', href: '/quickstart', icon: Rocket },
      { name: 'API Reference', href: '/api-reference', icon: BookOpen },
    ],
  },
]

export default function Layout() {
  const location = useLocation()

  // Global indexing completion/failure toasts — fires regardless of active page
  useIndexingToasts()

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const stored = localStorage.getItem('sidebarCollapsed')
    return stored === 'true'
  })

  const [mobileOpen, setMobileOpen] = useState(false)

  // Persist sidebar state
  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', String(sidebarCollapsed))
  }, [sidebarCollapsed])

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const SidebarContent = ({ collapsed = false }: { collapsed?: boolean }) => (
    <div className="flex flex-col h-full bg-card">
      {/* Logo */}
      <div className="h-16 flex items-center justify-center border-b border-border flex-shrink-0">
        {collapsed ? (
          <img src="/agentbase-logo.png" alt="Agentbase" className="h-8 w-8 object-contain" />
        ) : (
          <div className="px-4 flex items-center gap-2">
            <img src="/agentbase-logo.png" alt="Agentbase" className="h-10 w-10 object-contain" />
            <div className="flex flex-col leading-tight">
              <span className="text-lg font-semibold text-foreground">Agentbase</span>
              <span className="text-[10px] text-muted-foreground">kb for agents</span>
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className={cn(
        'flex-1 py-4',
        collapsed ? 'px-2 overflow-visible' : 'px-4 overflow-y-auto'
      )}>
        {collapsed ? (
          navigation.map((section, sectionIdx) => (
            <div key={section.label}>
              {sectionIdx > 0 && <Separator className="my-2" />}
              <div className="space-y-1">
                {section.items.map((item) => (
                  <Tooltip key={item.name}>
                    <TooltipTrigger asChild>
                      <NavLink
                        to={item.href}
                        className={({ isActive }) =>
                          cn(
                            'flex items-center justify-center py-2 px-2 text-sm font-medium rounded-md transition-colors',
                            isActive
                              ? 'bg-primary text-primary-foreground'
                              : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                          )
                        }
                      >
                        <item.icon className="h-5 w-5" />
                      </NavLink>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      {item.name}
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </div>
          ))
        ) : (
          navigation.map((section) => (
            <div key={section.label} className="mb-3">
              <div className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                {section.label}
              </div>
              <div className="space-y-1">
                {section.items.map((item) => (
                  <NavLink
                    key={item.name}
                    to={item.href}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center py-2 px-3 text-sm font-medium rounded-md transition-colors',
                        isActive
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      )
                    }
                  >
                    <item.icon className="h-5 w-5 mr-3" />
                    {item.name}
                  </NavLink>
                ))}
              </div>
            </div>
          ))
        )}
      </nav>

      {/* Footer with collapse toggle - Only on desktop */}
      <div className="border-t border-border flex-shrink-0 hidden md:block">
        <Button
          variant="ghost"
          className={cn(
            'w-full py-3 rounded-none',
            collapsed ? 'justify-center px-2' : 'px-4 justify-start'
          )}
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <ChevronRight className="h-5 w-5" />
          ) : (
            <>
              <ChevronLeft className="h-5 w-5 mr-2" />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </Button>
        {!collapsed && (
          <div className="px-4 pb-3 text-xs text-muted-foreground">
            Agentbase v0.3.0
          </div>
        )}
      </div>
    </div>
  )

  return (
    <TooltipProvider>
      <div className="flex h-screen bg-background overflow-hidden">
        {/* Desktop Sidebar */}
        <div
          className={cn(
            'hidden md:flex border-r border-border flex-col transition-all duration-300',
            sidebarCollapsed ? 'w-16 overflow-visible' : 'w-64'
          )}
        >
          <SidebarContent collapsed={sidebarCollapsed} />
        </div>

        {/* Mobile Header & Content Wrapper */}
        <div className="flex-1 flex flex-col h-full overflow-hidden w-full">
          {/* Mobile Header */}
          <div className="md:hidden h-14 flex items-center px-4 border-b border-border bg-card flex-shrink-0">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="-ml-2">
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="p-0 w-72">
                <SidebarContent collapsed={false} />
              </SheetContent>
            </Sheet>
            <div className="ml-2 flex items-center gap-2">
              <img src="/agentbase-logo.png" alt="Agentbase" className="h-8 w-8 object-contain" />
              <div className="flex flex-col leading-tight">
                <span className="font-semibold text-lg text-foreground">Agentbase</span>
                <span className="text-[10px] text-muted-foreground">kb for agents</span>
              </div>
            </div>
          </div>

          {/* Main content */}
          <main className="flex-1 overflow-hidden relative">
            <Outlet />
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}


import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  List,
  Layers,
  FileUp,
  BarChart2,
  Briefcase,
  Settings,
  type LucideIcon,
} from 'lucide-react'

interface NavItemProps {
  to: string
  icon: LucideIcon
  label: string
  end?: boolean
}

function NavItem({ to, icon: Icon, label, end }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      aria-label={label}
      className={({ isActive }) =>
        `relative w-9 h-9 flex items-center justify-center rounded-lg transition-colors group ` +
        (isActive
          ? 'bg-zinc-100 text-zinc-900'
          : 'text-zinc-400 hover:bg-zinc-50 hover:text-zinc-700')
      }
    >
      <Icon className="w-4 h-4" />
      <span className="absolute left-10 top-1/2 -translate-y-1/2 bg-zinc-900 text-white text-xs whitespace-nowrap px-2 py-1 rounded-md opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none z-50">
        {label}
      </span>
    </NavLink>
  )
}

export function Sidebar() {
  return (
    <aside className="w-14 shrink-0 bg-white border-r border-zinc-200 flex flex-col items-center py-4 gap-1">
      {/* Logo mark */}
      <div className="w-8 h-8 rounded-lg bg-zinc-900 flex items-center justify-center mb-3">
        <span className="text-white text-xs font-bold">S</span>
      </div>

      {/* Bookkeeping */}
      <NavItem to="/" icon={LayoutDashboard} label="Dashboard" end />
      <NavItem to="/transactions" icon={List} label="Transactions" />
      <NavItem to="/accounts" icon={Layers} label="Accounts" />

      <div className="w-6 border-t border-zinc-100 my-1" />

      <NavItem to="/import" icon={FileUp} label="Bank Import" />

      <div className="w-6 border-t border-zinc-100 my-1" />

      {/* Reports & Portfolio */}
      <NavItem to="/reports" icon={BarChart2} label="Reports" />
      <NavItem to="/portfolio" icon={Briefcase} label="Portfolio" />

      {/* Settings pinned to bottom */}
      <div className="flex-1" />
      <NavItem to="/settings" icon={Settings} label="Settings" />
    </aside>
  )
}

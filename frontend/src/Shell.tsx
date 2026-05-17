import { Outlet } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { ChatSidebar } from './components/ChatSidebar'

export function Shell() {
  return (
    <div className="flex h-screen overflow-hidden bg-zinc-50">
      <Sidebar />
      <div className="flex-1 overflow-y-auto min-w-0">
        <Outlet />
      </div>
      <ChatSidebar />
    </div>
  )
}

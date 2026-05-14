import { Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Accounts from './pages/Accounts'
import AccountDetail from './pages/AccountDetail'
import Import from './pages/Import'
import Reports from './pages/Reports'
import Portfolio from './pages/Portfolio'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/transactions" element={<Transactions />} />
      <Route path="/accounts" element={<Accounts />} />
      <Route path="/accounts/:id" element={<AccountDetail />} />
      <Route path="/import" element={<Import />} />
      <Route path="/reports" element={<Reports />} />
      <Route path="/portfolio" element={<Portfolio />} />
      <Route path="/settings" element={<Settings />} />
    </Routes>
  )
}

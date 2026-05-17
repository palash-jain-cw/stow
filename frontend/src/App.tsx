import { Routes, Route } from 'react-router-dom'
import { Shell } from './Shell'
import { RequireSetup } from './components/RequireSetup'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Accounts from './pages/Accounts'
import Reports from './pages/Reports'
import Portfolio from './pages/Portfolio'
import Settings from './pages/Settings'
import Onboarding from './pages/Onboarding'

export default function App() {
  return (
    <Routes>
      <Route path="/onboarding" element={<Onboarding />} />
      <Route element={<RequireSetup />}>
        <Route element={<Shell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/accounts" element={<Accounts />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Route>
    </Routes>
  )
}

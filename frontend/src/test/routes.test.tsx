import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '../App'

function renderAt(path: string) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

test('/ renders Dashboard', () => {
  renderAt('/')
  expect(screen.getByRole('heading', { name: /dashboard/i })).toBeInTheDocument()
})

test('/transactions renders Transactions', () => {
  renderAt('/transactions')
  expect(screen.getByRole('heading', { name: /transactions/i })).toBeInTheDocument()
})

test('/accounts renders Accounts', () => {
  renderAt('/accounts')
  expect(screen.getByRole('heading', { name: /accounts/i })).toBeInTheDocument()
})

test('/accounts/:id renders AccountDetail', () => {
  renderAt('/accounts/1')
  expect(screen.getByRole('heading', { name: /account detail/i })).toBeInTheDocument()
})

test('/import renders Import', () => {
  renderAt('/import')
  expect(screen.getByRole('heading', { name: /import/i })).toBeInTheDocument()
})

test('/reports renders Reports', () => {
  renderAt('/reports')
  expect(screen.getByRole('heading', { name: /reports/i })).toBeInTheDocument()
})

test('/portfolio renders Portfolio', () => {
  renderAt('/portfolio')
  expect(screen.getByRole('heading', { name: /portfolio/i })).toBeInTheDocument()
})

test('/settings renders Settings', () => {
  renderAt('/settings')
  expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument()
})

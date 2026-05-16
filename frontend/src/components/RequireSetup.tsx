import { Outlet, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, queryKeys } from '../api/api'

interface FinancialYear { id: number }

export function RequireSetup() {
  const { data: fys } = useQuery<FinancialYear[]>({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<FinancialYear[]>('/financial-years'),
    staleTime: 0,
  })

  // Only redirect once we have a confirmed empty response; render normally while loading
  if (fys !== undefined && fys.length === 0) {
    return <Navigate to="/onboarding" replace />
  }
  return <Outlet />
}

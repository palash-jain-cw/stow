import { Outlet, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, queryKeys } from '../api/api'

interface FinancialYear { id: number }

export function RequireSetup() {
  const { data: fys, isPending } = useQuery<FinancialYear[]>({
    queryKey: queryKeys.financialYears.all(),
    queryFn: () => api.get<FinancialYear[]>('/financial-years'),
    staleTime: 0,
  })

  if (isPending) return null
  if (fys!.length === 0) return <Navigate to="/onboarding" replace />
  return <Outlet />
}

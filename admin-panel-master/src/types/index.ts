export interface Client {
  id: number
  email: string
  name: string | null
  phone: string | null
  telegram_username: string | null
  applications_balance: number
  created_at: string
}

export interface Application {
  id: number
  user_id: number
  site: string
  region: string | null
  region_id: number | null
  keywords: string | null
  status: string | null
  manager_name: string | null
  audit: boolean
  google: boolean
  yandex: boolean
  keywords_selection: boolean
  client_email: string | null
  created_at: string
  total_visits: []
}

export interface Payment {
  id: number
  payment_id: string
  tariff: string
  amount: number
  status: string
  created_at: string
}

export interface BotTask {
  id: number
  keyword: string
  target_site: string
  daily_visit_target: number
  total_visit_target: number
  daily_visit_count: number
  successful_visits: number | null
  failed_visits: number | null
  proxy_url: string | null
  proxy_port_id: number | null
  is_paused: boolean
}

export interface TeamMember {
  id: number
  name: string
  email: string
  role: string
  is_active: boolean
  created_at: string
}

export interface DashboardStats {
  clients_count: number
  pending_applications: number
  total_applications: number
  total_revenue: number
  confirmed_payments: number
}

export interface ProjectProxy {
  id: number
  application_id: number
  proxy_url: string
  created_at: string
}

export interface ASocksRegion {
  id: number
  name: string
}

export interface ProxyResult {
  id: number
  proxy_url: string
}

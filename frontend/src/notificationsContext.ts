import { createContext, useContext } from 'react'
import type { AppNotification } from './api'

export interface NotificationsState { unread: number; items: AppNotification[]; refresh: () => void; read: (id: number) => Promise<void>; readAll: () => Promise<void> }
export const NotificationsContext = createContext<NotificationsState>({ unread: 0, items: [], refresh: () => undefined, read: async () => undefined, readAll: async () => undefined })
export const useNotifications = () => useContext(NotificationsContext)

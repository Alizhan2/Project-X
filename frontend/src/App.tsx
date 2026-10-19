import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import RequireAuth from './components/RequireAuth'
import Account from './pages/Account'
import Book from './pages/Book'
import BookingDetail from './pages/BookingDetail'
import Journey from './pages/Journey'
import MyJourneys from './pages/MyJourneys'
import Notifications from './pages/Notifications'
import Pay from './pages/Pay'
import RequireRole from './components/RequireRole'
import NewService from './pages/operator/NewService'
import ServiceDetail from './pages/operator/ServiceDetail'
import Services from './pages/operator/Services'
import Search from './pages/Search'
import Status from './pages/Status'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Search />} />
        <Route path="journey" element={<Journey />} />
        <Route path="login" element={<Account mode="login" />} />
        <Route path="register" element={<Account mode="register" />} />
        <Route element={<RequireAuth />}>
          <Route path="book" element={<Book />} />
          <Route path="booking/:ref/pay" element={<Pay />} />
          <Route path="booking/:ref" element={<BookingDetail />} />
          <Route path="journeys" element={<MyJourneys />} />
          <Route path="notifications" element={<Notifications />} />
        </Route>
        <Route element={<RequireRole role="operator" />}>
          <Route path="operator" element={<Services />} />
          <Route path="operator/new" element={<NewService />} />
          <Route path="operator/services/:id" element={<ServiceDetail />} />
        </Route>
        <Route path="status" element={<Status />} />
        <Route path="*" element={<p>Page not found.</p>} />
      </Route>
    </Routes>
  )
}

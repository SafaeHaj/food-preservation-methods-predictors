import { Outlet } from 'react-router-dom'
import ProjectSidebar from '../components/ProjectSidebar'

export default function ProjectLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <ProjectSidebar />
      <main className="flex-1 overflow-y-auto bg-[#f8f9fb] min-w-0 flex flex-col">
        <Outlet />
      </main>
    </div>
  )
}

"use client";

import * as React from "react";
import { Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/form-error";
import { PageHeader, PageBody, Section } from "@/components/page-shell";
import { initialsOf, useSession } from "@/components/session-store";
import { ApiError, api, resolveAvatarUrl } from "@/lib/api";

const MAX_MB = 5;

export function AccountView() {
  const { user, setUser } = useSession();
  const fileRef = React.useRef<HTMLInputElement>(null);

  const [name, setName] = React.useState(user?.name ?? "");
  const [institution, setInstitution] = React.useState(user?.institution ?? "");
  const [role, setRole] = React.useState(user?.role ?? "");
  const [savingProfile, setSavingProfile] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);

  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [passwordError, setPasswordError] = React.useState<string | null>(null);
  const [savingPassword, setSavingPassword] = React.useState(false);

  if (!user) return null;
  const avatar = resolveAvatarUrl(user.avatar_url);

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    setSavingProfile(true);
    try {
      setUser(await api.updateProfile({ name, institution, role }));
      toast.success("Profile updated");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Couldn't save your profile.");
    } finally {
      setSavingProfile(false);
    }
  }

  async function onAvatarSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset immediately so picking the same file twice still fires onChange.
    event.target.value = "";
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast.error("Choose an image file.");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      toast.error(`Image must be ${MAX_MB} MB or smaller.`);
      return;
    }

    setUploading(true);
    try {
      setUser(await api.uploadAvatar(file));
      toast.success("Photo updated");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Couldn't upload that image.");
    } finally {
      setUploading(false);
    }
  }

  async function removePhoto() {
    setUploading(true);
    try {
      setUser(await api.removeAvatar());
      toast.success("Photo removed");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Couldn't remove the photo.");
    } finally {
      setUploading(false);
    }
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setPasswordError(null);
    setSavingPassword(true);
    try {
      await api.changePassword({ current_password: currentPassword, new_password: newPassword });
      setCurrentPassword("");
      setNewPassword("");
      toast.success("Password changed");
    } catch (err) {
      setPasswordError(err instanceof ApiError ? err.detail : "Couldn't change your password.");
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <PageBody>
      <PageHeader title="Account" description="Manage your profile and sign-in details." />

      <div className="flex max-w-[560px] flex-col gap-8">
        <Section title="Profile photo">
          <div className="flex items-center gap-4">
            <Avatar className="size-14 rounded-lg">
              {avatar && <AvatarImage src={avatar} alt="" />}
              <AvatarFallback className="rounded-lg bg-primary text-[1rem] font-medium text-primary-foreground">
                {initialsOf(user.name)}
              </AvatarFallback>
            </Avatar>

            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={uploading}
                  onClick={() => fileRef.current?.click()}
                >
                  {uploading ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Upload className="size-3.5" />
                  )}
                  {avatar ? "Replace" : "Upload"}
                </Button>
                {avatar && (
                  <Button
                    variant="destructive-ghost"
                    size="sm"
                    disabled={uploading}
                    onClick={() => void removePhoto()}
                  >
                    <Trash2 className="size-3.5" />
                    Remove
                  </Button>
                )}
              </div>
              <p className="type-caption text-subtle-foreground">
                JPEG, PNG or WebP · up to {MAX_MB} MB · cropped square
              </p>
            </div>

            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="sr-only"
              onChange={onAvatarSelected}
              aria-label="Upload profile photo"
            />
          </div>
        </Section>

        <Section title="Profile">
          <form onSubmit={saveProfile} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="acct-name">Full name</Label>
              <Input id="acct-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="acct-email">Email</Label>
              <Input id="acct-email" value={user.email} disabled readOnly />
              <p className="type-caption text-subtle-foreground">
                Email is used to sign in and can&apos;t be changed here.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="acct-institution">Institution</Label>
                <Input
                  id="acct-institution"
                  value={institution}
                  onChange={(e) => setInstitution(e.target.value)}
                  placeholder="McGill University"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="acct-role">Role</Label>
                <Input
                  id="acct-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="Graduate researcher"
                />
              </div>
            </div>
            <div>
              <Button type="submit" size="sm" disabled={savingProfile}>
                {savingProfile && <Loader2 className="size-3.5 animate-spin" />}
                Save changes
              </Button>
            </div>
          </form>
        </Section>

        <Section title="Password">
          <form onSubmit={changePassword} className="flex flex-col gap-4">
            <FormError message={passwordError} />
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="acct-current">Current password</Label>
              <Input
                id="acct-current"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="acct-new">New password</Label>
              <Input
                id="acct-new"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
              <p className="type-caption text-subtle-foreground">At least 8 characters</p>
            </div>
            <div>
              <Button type="submit" variant="outline" size="sm" disabled={savingPassword}>
                {savingPassword && <Loader2 className="size-3.5 animate-spin" />}
                Change password
              </Button>
            </div>
          </form>
        </Section>
      </div>
    </PageBody>
  );
}

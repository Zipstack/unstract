import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QueryView } from "@v1/components/patterns/QueryView";
import { Button, IconButton } from "@v1/components/ui/button";
import { CopyButton } from "@v1/components/ui/code";
import { SkeletonTableRows } from "@v1/components/ui/feedback";
import { Radio, RadioGroup } from "@v1/components/ui/toggles";
import { ACTION_ICONS } from "@v1/lib/icons";
import { toast } from "@v1/lib/notify";
import { SettingsSection } from "@v1/pages/prompt-studio/settings/SettingsSection";
import { confirmDestructive } from "@v1/pages/prompt-studio/settings/standins";
import {
  deleteProfile,
  type LlmProfile,
  MAX_PROFILES,
  promptProfileKeys,
  promptProfileQueries,
  setDefaultProfile,
} from "@v1/services/promptProfiles";
import { promptStudioToolKeys } from "@v1/services/promptStudioTool";
import { type JSX, useState } from "react";
import { ProfileForm } from "./ProfileForm";

export type ProfilesSectionProps = Readonly<{
  toolId: string;
  readOnly: boolean;
  /** True while the add or edit form has changes, for the tab's leave guard. */
  onDirtyChange: (dirty: boolean) => void;
}>;

/** What the section shows: the list (null), the add form, or one profile's edit form. */
type Editing = null | "new" | LlmProfile;

const COLUMNS = [
  "Name",
  "LLM",
  "Embedding Model",
  "Vector Database",
  "Text Extractor",
] as const;

/** LLM Profiles (frames D09, D10): the project's profiles and its default. */
export function ProfilesSection({
  toolId,
  readOnly,
  onDirtyChange,
}: ProfilesSectionProps): JSX.Element {
  const query = useQuery(promptProfileQueries.list(toolId));
  const [editing, setEditing] = useState<Editing>(null);

  return (
    <SettingsSection id="llm-profiles" title={sectionTitle(editing)}>
      <QueryView query={query} loading={<SkeletonTableRows rows={3} />}>
        {(profiles) =>
          editing === null ? (
            <ProfileList
              toolId={toolId}
              profiles={profiles}
              readOnly={readOnly}
              onAdd={() => setEditing("new")}
              onEdit={setEditing}
            />
          ) : (
            <ProfileEditor
              toolId={toolId}
              profiles={profiles}
              editing={editing}
              onDirtyChange={onDirtyChange}
              onClose={() => setEditing(null)}
            />
          )
        }
      </QueryView>
    </SettingsSection>
  );
}

function sectionTitle(editing: Editing): string {
  if (editing === null) {
    return "LLM Profile Settings";
  }
  return editing === "new" ? "Add New LLM Profile" : "Edit LLM Profile";
}

/** The add or edit form, drawn in place of the list (frame D10). */
function ProfileEditor({
  toolId,
  profiles,
  editing,
  onDirtyChange,
  onClose,
}: Readonly<{
  toolId: string;
  profiles: readonly LlmProfile[];
  editing: "new" | LlmProfile;
  onDirtyChange: (dirty: boolean) => void;
  onClose: () => void;
}>): JSX.Element {
  const queryClient = useQueryClient();
  // Its failure gets its own message below, not the generic one.
  const makeDefault = useSetDefault(toolId, { notify: false });
  const profile = editing === "new" ? undefined : editing;
  const others = profiles.filter((p) => p.profile_id !== profile?.profile_id);
  return (
    <ProfileForm
      toolId={toolId}
      profile={profile}
      takenNames={others.map((p) => p.profile_name)}
      onCancel={onClose}
      onDirtyChange={onDirtyChange}
      onSaved={(saved) => {
        const refresh = () =>
          queryClient.invalidateQueries({
            queryKey: promptProfileKeys.list(toolId),
          });
        // A project's first profile becomes its default, as in v0. The list
        // refreshes after that, so it cannot read the profile before it is.
        if (profiles.length === 0) {
          void makeDefault
            .mutateAsync(saved.profile_id)
            .catch(() => {
              toast.warning("Profile saved, but it is not the default", {
                description: "Choose it as the default to run prompts.",
              });
            })
            .finally(refresh);
        } else {
          void refresh();
        }
        onClose();
      }}
    />
  );
}

function useSetDefault(
  toolId: string,
  { notify = true }: Readonly<{ notify?: boolean }> = {},
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profileId: string) => setDefaultProfile(toolId, profileId),
    meta: { notify },
    onSuccess: (defaultId) => {
      queryClient.setQueryData<LlmProfile[]>(
        promptProfileKeys.list(toolId),
        (rows) =>
          rows?.map((p) => ({ ...p, is_default: p.profile_id === defaultId })),
      );
      // The project carries its default too (prompts and indexing read it).
      void queryClient.invalidateQueries({
        queryKey: promptStudioToolKeys.detail(toolId),
      });
    },
  });
}

function ProfileList({
  toolId,
  profiles,
  readOnly,
  onAdd,
  onEdit,
}: Readonly<{
  toolId: string;
  profiles: readonly LlmProfile[];
  readOnly: boolean;
  onAdd: () => void;
  onEdit: (profile: LlmProfile) => void;
}>): JSX.Element {
  const queryClient = useQueryClient();
  const makeDefault = useSetDefault(toolId);
  const remove = useMutation({
    mutationFn: (profileId: string) => deleteProfile(profileId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: promptProfileKeys.list(toolId),
      }),
  });
  const defaultId = profiles.find((p) => p.is_default)?.profile_id ?? "";
  const atCap = profiles.length >= MAX_PROFILES;

  const askDelete = async (profile: LlmProfile) => {
    const ok = await confirmDestructive({
      title: `Delete ${profile.profile_name}?`,
      description: "The LLM profile will be permanently deleted.",
      confirmLabel: "Delete",
    });
    if (ok) {
      remove.mutate(profile.profile_id);
    }
  };

  return (
    <div className="ui:grid ui:gap-3">
      {profiles.length === 0 ? (
        <p className="ui:rounded-lg ui:border ui:p-4 ui:text-body-small ui:text-muted-foreground">
          No LLM profiles yet. Prompts run and documents index only with a
          default profile, so add one to start.
        </p>
      ) : (
        // ponytail: a plain table until P1-T11's data table lands; at most four rows, no sorting or paging.
        <RadioGroup
          aria-label="Default profile"
          value={defaultId}
          disabled={readOnly || makeDefault.isPending}
          onValueChange={(id) => makeDefault.mutate(id)}
          className="ui:overflow-x-auto ui:rounded-lg ui:border ui:bg-card"
        >
          <table className="ui:w-full ui:text-caption">
            <thead className="ui:bg-muted ui:text-overline ui:uppercase ui:text-muted-foreground">
              <tr>
                {COLUMNS.map((c) => (
                  <th
                    key={c}
                    scope="col"
                    className="ui:px-4 ui:py-3 ui:text-left ui:font-semibold"
                  >
                    {c}
                  </th>
                ))}
                <th
                  scope="col"
                  className="ui:px-4 ui:py-3 ui:text-left ui:font-semibold"
                >
                  Actions
                </th>
                <th
                  scope="col"
                  className="ui:px-4 ui:py-3 ui:text-left ui:font-semibold"
                >
                  Default
                </th>
              </tr>
            </thead>
            <tbody className="ui:divide-y">
              {profiles.map((p) => (
                <tr key={p.profile_id} className="ui:h-12 ui:text-foreground">
                  <td className="ui:px-4 ui:font-medium">{p.profile_name}</td>
                  <td className="ui:px-4 ui:text-muted-foreground">{p.llm}</td>
                  <td className="ui:px-4 ui:text-muted-foreground">
                    {p.embedding_model}
                  </td>
                  <td className="ui:px-4 ui:text-muted-foreground">
                    {p.vector_store}
                  </td>
                  <td className="ui:px-4 ui:text-muted-foreground">
                    {p.x2text}
                  </td>
                  <td className="ui:px-4">
                    <div className="ui:flex ui:items-center ui:gap-1">
                      <CopyButton
                        data-testid={`ps-llm-profile-copy-id-${p.profile_id}`}
                        text={p.profile_id}
                        label={`Copy the profile ID of ${p.profile_name}`}
                        copiedMessage="Profile ID copied to clipboard"
                      />
                      {readOnly ? null : (
                        <>
                          <IconButton
                            size="sm"
                            icon={ACTION_ICONS.edit}
                            aria-label={`Edit ${p.profile_name}`}
                            data-testid={`ps-llm-profile-edit-${p.profile_id}`}
                            onClick={() => onEdit(p)}
                          />
                          <IconButton
                            size="sm"
                            icon={ACTION_ICONS.delete}
                            aria-label={
                              p.is_default
                                ? `${p.profile_name} is the default and cannot be deleted`
                                : `Delete ${p.profile_name}`
                            }
                            title={
                              p.is_default
                                ? "Default profile cannot be deleted"
                                : undefined
                            }
                            disabled={p.is_default || remove.isPending}
                            className="ui:text-destructive"
                            data-testid={`ps-llm-profile-delete-${p.profile_id}`}
                            onClick={() => void askDelete(p)}
                          />
                        </>
                      )}
                    </div>
                  </td>
                  <td className="ui:px-4">
                    <Radio
                      value={p.profile_id}
                      aria-label={`Make ${p.profile_name} the default`}
                      data-testid={`ps-llm-profile-select-default-${p.profile_id}`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </RadioGroup>
      )}
      {readOnly ? null : (
        <div className="ui:flex ui:items-center ui:justify-end ui:gap-3">
          {atCap ? (
            <span className="ui:text-caption ui:text-muted-foreground">
              A project has at most {MAX_PROFILES} profiles.
            </span>
          ) : null}
          <Button
            size="lg"
            leadingIcon={ACTION_ICONS.add}
            disabled={atCap}
            data-testid="ps-llm-profile-add"
            onClick={onAdd}
          >
            Add New LLM Profile
          </Button>
        </div>
      )}
    </div>
  );
}

import warnings

import awkward

from coffea.nanoevents import transforms
from coffea.nanoevents.schemas.base import (
    BaseSchema,
    counts2nestedindex_form,
    counts2offsets,
    local2globalindex,
    nestedindex_form,
    zip_depth1,
    zip_depth2,
)


def _key_formatter(prefix, form_key, form, attribute):
    if attribute == "offsets":
        form_key += "%2C%21offsets"
    return prefix + f"/{attribute}/{form_key}"


# REMOVE ABOVE


class NanoAODSchema(BaseSchema):
    """NanoAOD schema builder

    The NanoAOD schema is built from all branches found in the supplied file, based on
    the naming pattern of the branches. The following additional arrays are constructed:

    - Any branches named ``n{name}`` are assumed to be counts branches and converted to offsets ``o{name}``
    - Any local index branches with names matching ``{source}_{target}Idx*`` are converted to global indexes for the event chunk (postfix ``G``)
    - Any `nested_items` are constructed, if the necessary branches are available
    - Any `special_items` are constructed, if the necessary branches are available

    From those arrays, NanoAOD collections are formed as collections of branches grouped by name, where:

    - one branch exists named ``name`` and no branches start with ``name_``, interpreted as a single flat array;
    - one branch exists named ``name``, one named ``n{name}``, and no branches start with ``name_``, interpreted as a single jagged array;
    - no branch exists named ``{name}`` and many branches start with ``name_*``, interpreted as a flat table; or
    - one branch exists named ``n{name}`` and many branches start with ``name_*``, interpreted as a jagged table.

    Collections are assigned mixin types according to the `mixins` mapping.
    All collections are then zipped into one `base.NanoEvents` record and returned.

    There is a class-level variable ``warn_missing_crossrefs`` which will alter the behavior of
    NanoAODSchema. If warn_missing_crossrefs is true then when a missing global index cross-ref
    target is encountered a warning will be issued. Regardless, the cross-reference is dropped.

    The same holds for ``error_missing_events_id``. If error_missing_events_id is true, then when the 'run', 'event',
    or 'luminosityBlock' fields are missing, an exception will be thrown; if it is false, just a warning will be issued.
    """

    __dask_capable__ = True
    warn_missing_crossrefs = True  # If True, issues a warning when a missing global index cross-ref target is encountered
    error_missing_event_ids = True  # If True, raises an exception when 'run', 'event', or 'luminosityBlock' fields are missing

    event_ids = ["run", "luminosityBlock", "event"]
    """List of NanoAOD event IDs
    """

    mixins = {
        "CaloMET": "MissingET",
        "ChsMET": "MissingET",
        "GenMET": "MissingET",
        "MET": "MissingET",
        "METFixEE2017": "MissingET",
        "PuppiMET": "MissingET",
        "RawMET": "MissingET",
        "RawPuppiMET": "MissingET",
        "TkMET": "MissingET",
        # pseudo-lorentz: pt, eta, phi, mass=0
        "IsoTrack": "PtEtaPhiMCollection",
        "SoftActivityJet": "PtEtaPhiMCollection",
        "TrigObj": "PtEtaPhiMCollection",
        # True lorentz: pt, eta, phi, mass
        "FatJet": "FatJet",
        "GenDressedLepton": "PtEtaPhiMCollection",
        "GenIsolatedPhoton": "PtEtaPhiMCollection",
        "GenJet": "PtEtaPhiMCollection",
        "GenJetAK8": "PtEtaPhiMCollection",
        "Jet": "Jet",
        "LHEPart": "PtEtaPhiMCollection",
        "SubGenJetAK8": "PtEtaPhiMCollection",
        "SubJet": "PtEtaPhiMCollection",
        # Candidate: lorentz + charge
        "Electron": "Electron",
        "LowPtElectron": "LowPtElectron",
        "Muon": "Muon",
        "Photon": "Photon",
        "FsrPhoton": "FsrPhoton",
        "Tau": "Tau",
        "GenVisTau": "GenVisTau",
        # special
        "GenPart": "GenParticle",
        "PV": "Vertex",
        "SV": "SecondaryVertex",
    }
    """Default configuration for mixin types, based on the collection name.

    The types are implemented in the `coffea.nanoevents.methods.nanoaod` module.
    """
    all_cross_references = {
        "Electron_genPartIdx": "GenPart",
        "Electron_jetIdx": "Jet",
        "Electron_photonIdx": "Photon",
        "LowPtElectron_electronIdx": "Electron",
        "LowPtElectron_genPartIdx": "GenPart",
        "LowPtElectron_photonIdx": "Photon",
        "FatJet_genJetAK8Idx": "GenJetAK8",
        "FatJet_subJetIdx1": "SubJet",
        "FatJet_subJetIdx2": "SubJet",
        "FsrPhoton_muonIdx": "Muon",
        "GenPart_genPartIdxMother": "GenPart",
        "GenVisTau_genPartIdxMother": "GenPart",
        "Jet_electronIdx1": "Electron",
        "Jet_electronIdx2": "Electron",
        "Jet_genJetIdx": "GenJet",
        "Jet_muonIdx1": "Muon",
        "Jet_muonIdx2": "Muon",
        "Muon_fsrPhotonIdx": "FsrPhoton",
        "Muon_genPartIdx": "GenPart",
        "Muon_jetIdx": "Jet",
        "Photon_electronIdx": "Electron",
        "Photon_genPartIdx": "GenPart",
        "Photon_jetIdx": "Jet",
        "Tau_genPartIdx": "GenPart",
        "Tau_jetIdx": "Jet",
    }
    """Cross-references, where an index is to be interpreted with respect to another collection

    Each such cross-reference will be converted to a global indexer, so that arbitrarily sliced events
    can still resolve the indirection back the parent events
    """
    nested_items = {
        "FatJet_subJetIdxG": ["FatJet_subJetIdx1G", "FatJet_subJetIdx2G"],
        "Jet_muonIdxG": ["Jet_muonIdx1G", "Jet_muonIdx2G"],
        "Jet_electronIdxG": ["Jet_electronIdx1G", "Jet_electronIdx2G"],
    }
    """Nested collections, where nesting is accomplished by a fixed-length set of indexers"""
    nested_index_items = {
        "Jet_pFCandsIdxG": ("Jet_nConstituents", "JetPFCands"),
        "FatJet_pFCandsIdxG": ("FatJet_nConstituents", "FatJetPFCands"),
        "GenJet_pFCandsIdxG": ("GenJet_nConstituents", "GenJetCands"),
        "GenFatJet_pFCandsIdxG": ("GenJetAK8_nConstituents", "GenFatJetCands"),
    }
    """Nested collections, where nesting is accomplished by assuming the target can be unflattened according to a source counts"""
    special_items = {
        "GenPart_distinctParentIdxG": (
            transforms.distinctParent_form,
            ("GenPart_genPartIdxMotherG", "GenPart_pdgId"),
        ),
        "GenPart_childrenIdxG": (
            transforms.children_form,
            (
                "oGenPart",
                "GenPart_genPartIdxMotherG",
            ),
        ),
        "GenPart_distinctChildrenIdxG": (
            transforms.children_form,
            (
                "oGenPart",
                "GenPart_distinctParentIdxG",
            ),
        ),
        "GenPart_distinctChildrenDeepIdxG": (
            transforms.distinctChildrenDeep_form,
            (
                "oGenPart",
                "GenPart_genPartIdxMotherG",
                "GenPart_pdgId",
            ),
        ),
    }
    """Special arrays, where the callable and input arrays are specified in the value"""

    def __init__(self, base_form, tree, version="latest"):
        super().__init__(base_form)
        self._version = version
        self.cross_references = dict(self.all_cross_references)
        if version == "latest":
            pass
        else:
            if int(version) < 7:
                del self.cross_references["FatJet_genJetAK8Idx"]
            if int(version) < 6:
                del self.cross_references["FsrPhoton_muonIdx"]
                del self.cross_references["Muon_fsrPhotonIdx"]

        # TTree -> dict[str, ak.Array]
        preconstructed_array = tree.arrays(library="ak", how=dict, ak_add_doc=True)
        self._array = self._build_collections(
            preconstructed_array.keys(), preconstructed_array.values()
        )

    @classmethod
    def v7(cls, base_form):
        """Build the NanoEvents assuming NanoAODv7

        For example, one can use ``NanoEventsFactory.from_root("file.root", schemaclass=NanoAODSchema.v7)``
        to ensure NanoAODv7 compatibility.

        Returns
        -------
            out: NanoAODSchema
                Schema assuming NanoAODv7
        """
        return cls(base_form, version="7")

    @classmethod
    def v6(cls, base_form):
        """Build the NanoEvents assuming NanoAODv6

        Returns
        -------
            out: NanoAODSchema
                Schema assuming NanoAODv6
        """
        return cls(base_form, version="6")

    @classmethod
    def v5(cls, base_form):
        """Build the NanoEvents assuming NanoAODv5

        Returns
        -------
            out: NanoAODSchema
                Schema assuming NanoAODv5
        """
        return cls(base_form, version="5")

    def _build_collections(self, field_names, input_contents):

        branches = {k: v for k, v in zip(field_names, input_contents)}

        # parse into high-level records (collections, list collections, and singletons)
        collections = {k.split("_")[0] for k in branches}

        # unique keys that start with "n" are short for number, we don't need them in the final schema
        collections -= {
            k for k in collections if k.startswith("n") and k[1:] in collections
        }
        isData = "GenPart" not in collections

        # Check the presence of the event_ids
        missing_event_ids = [
            event_id for event_id in self.event_ids if event_id not in branches
        ]
        if len(missing_event_ids) > 0:
            if self.error_missing_event_ids:
                raise RuntimeError(
                    f"There are missing event ID fields: {missing_event_ids} \n\n\
                    The event ID fields {self.event_ids} are necessary to perform sub-run identification \
                    (e.g. for corrections and sub-dividing data during different detector conditions),\
                    to cross-validate MC and Data (i.e. matching events for comparison), and to generate event displays. \
                    It's advised to never drop these branches from the dataformat.\n\n\
                    This error can be demoted to a warning by setting the class level variable error_missing_event_ids to False."
                )
            else:
                warnings.warn(
                    f"Missing event_ids : {missing_event_ids}",
                    RuntimeWarning,
                )

        # Create global index virtual arrays for indirection
        for indexer, target in self.all_cross_references.items():
            if target.startswith("Gen") and isData:
                continue
            if indexer not in branches:
                if self.warn_missing_crossrefs:
                    warnings.warn(
                        f"Missing cross-reference index for {indexer} => {target}",
                        RuntimeWarning,
                    )
                continue
            if "n" + target not in branches:
                if self.warn_missing_crossrefs:
                    warnings.warn(
                        f"Missing cross-reference target for {indexer} => {target}",
                        RuntimeWarning,
                    )
                continue
            # convert nWhatever to a global index
            # this used to be transforms.counts2offsets_form + transforms.local2global_form
            branches[indexer + "G"] = local2globalindex(
                branches[indexer], branches["n" + target]
            )

        # Create nested indexer from Idx1, Idx2, ... arrays
        for name, indexers in self.nested_items.items():
            if all(idx in branches for idx in indexers):
                branches[name] = nestedindex_form([branches[idx] for idx in indexers])

        # Create nested indexer from n* counts arrays
        for name, (local_counts, target) in self.nested_index_items.items():
            if local_counts in branches and "n" + target in branches:
                branches[name] = counts2nestedindex_form(
                    branches[local_counts], branches["n" + target]
                )

        # # Create any special arrays
        # for name, (fcn, args) in self.special_items.items():
        #     if all(k in branches for k in args):
        #         raise NotImplementedError
        #         # branches[name] = fcn(*(branches[k] for k in args))

        output = {}
        for name in collections:
            if "n" + name in branches and name not in branches:
                # list collection
                offsets = counts2offsets(branches["n" + name])
                offsets = awkward.index.Index(offsets)

                content = {
                    k[len(name) + 1 :]: v
                    for k, v in branches.items()
                    if k.startswith(name + "_")
                }
                output[name] = zip_depth2(
                    content,
                    offsets,
                    with_name=self.mixins.get(name, "NanoCollection"),
                    behavior=self.behavior(),
                )

            elif "n" + name in branches:
                # list singleton, can use branch's own offsets
                output[name] = branches[name]
            elif name in branches:
                # singleton
                output[name] = branches[name]
            else:
                # simple collection
                content = {
                    k[len(name) + 1 :]: v
                    for k, v in branches.items()
                    if k.startswith(name + "_")
                }
                output[name] = zip_depth1(
                    content,
                    with_name=NanoAODSchema.mixins.get(name, "NanoCollection"),
                    behavior=NanoAODSchema.behavior(),
                )

        # zipping once again
        final_output = zip_depth1(
            output, with_name="NanoEvents", behavior=NanoAODSchema.behavior()
        )

        # return output.keys(), output.values()
        return final_output

    @classmethod
    def behavior(cls):
        """Behaviors necessary to implement this schema (dict)"""
        from coffea.nanoevents.methods import nanoaod

        return nanoaod.behavior


class PFNanoAODSchema(NanoAODSchema):
    """PFNano schema builder

    PFNano is an extended NanoAOD format that includes PF candidates and secondary vertices
    More info at https://github.com/cms-jet/PFNano
    """

    mixins = {
        **NanoAODSchema.mixins,
        "JetSVs": "AssociatedSV",
        "FatJetSVs": "AssociatedSV",
        "GenJetSVs": "AssociatedSV",
        "GenFatJetSVs": "AssociatedSV",
        "JetPFCands": "AssociatedPFCand",
        "FatJetPFCands": "AssociatedPFCand",
        "GenJetCands": "AssociatedPFCand",
        "GenFatJetCands": "AssociatedPFCand",
        "PFCands": "PFCand",
        "GenCands": "PFCand",
    }
    all_cross_references = {
        **NanoAODSchema.all_cross_references,
        "FatJetPFCands_jetIdx": "FatJet",  # breaks pattern
        "FatJetPFCands_pFCandsIdx": "PFCands",
        "FatJetSVs_jetIdx": "FatJet",  # breaks pattern
        "FatJetSVs_sVIdx": "SV",
        "FatJet_electronIdx3SJ": "Electron",
        "FatJet_muonIdx3SJ": "Muon",
        "GenFatJetCands_jetIdx": "GenJetAK8",  # breaks pattern
        "GenFatJetCands_pFCandsIdx": "GenCands",  # breaks pattern
        "GenFatJetSVs_jetIdx": "GenJetAK8",  # breaks pattern
        "GenFatJetSVs_sVIdx": "SV",
        "GenJetCands_jetIdx": "GenJet",  # breaks pattern
        "GenJetCands_pFCandsIdx": "GenCands",  # breaks pattern
        "GenJetSVs_jetIdx": "GenJet",  # breaks pattern
        "GenJetSVs_sVIdx": "SV",
        "JetPFCands_jetIdx": "Jet",
        "JetPFCands_pFCandsIdx": "PFCands",
        "JetSVs_jetIdx": "Jet",
        "JetSVs_sVIdx": "SV",
        "SubJet_subGenJetAK8Idx": "SubGenJetAK8",
    }


class ScoutingNanoAODSchema(NanoAODSchema):
    """ScoutingNano schema builder

    ScoutingNano is a NanoAOD format that includes Scouting objects
    """

    mixins = {
        **NanoAODSchema.mixins,
        "ScoutingJet": "Jet",
        "ScoutingFatJet": "FatJet",
        "ScoutingMET": "MissingET",
        "ScoutingMuonNoVtxDisplacedVertex": "Vertex",
        "ScoutingMuonVtxDisplacedVertex": "Vertex",
        "ScoutingPrimaryVertex": "Vertex",
        "ScoutingElectron": "Electron",
        "ScoutingPhoton": "Photon",
        "ScoutingMuonNoVtx": "Muon",
        "ScoutingMuonVtx": "Muon",
    }

    all_cross_references = {**NanoAODSchema.all_cross_references}

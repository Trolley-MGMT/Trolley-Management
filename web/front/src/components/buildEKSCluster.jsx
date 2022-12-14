import React, { Component } from "react";
import YamlEditor from './yamlEditor';
import { oneDark } from "@codemirror/theme-one-dark";
import { Toast } from 'bootstrap/dist/js/bootstrap';

class CreateCluster extends Component {

  constructor(props) {
    super(props);
    this.state = {
      toastMessage: '',
      // selected
      nodesAmt: '1',
      version: '1.21',
      location: '',
      zone: [],
      subnet: [],
      helmInstall: [],
      expirationTime: '1',
      deploymentYAML: '',
      // needs to be populated
      locations: [],
      zones: [1,2],
      subnets: [],
      helmInstalls: [],
      // loading
      locationsIsLoading: true,
      zonesIsLoading: false,
      subnetsIsLoading: false,
      helmInstallsIsLoading: true
    }
  }

  async componentDidMount(){
    const { trolleyUrl, port } = this.props.appData;
    // Get locations/regions
    const url_locations = `http://${trolleyUrl}:${port}/fetch_regions?cluster_type=eks`;
    try {
      const response = await fetch(url_locations);
      if (!response.ok){
        const error = response.statusText;
        throw new Error(error);
      }
      const locations = await response.json();
      this.setState({ locations, location: locations[1], zonesIsLoading: true });
      await this.getZones(locations[1]);
    } catch(error) {
      console.log(error);
    } finally{
      this.setState({ locationsIsLoading: false })
    }
    // Get helm installs
    const url_helm = `http://${trolleyUrl}:${port}/fetch_helm_installs?names=True`;
    try {
      const response = await fetch(url_helm);
      if (!response.ok){
        const err = await response.text();
        throw new Error(err);
      }
      const helmInstalls = await response.json();
      this.setState({ helmInstalls });
    } catch(error) {
      console.log(error);
    } finally {
      this.setState({ helmInstallsIsLoading: false })
    }
  }

  async getZones(location) {
    const { trolleyUrl, port } = this.props.appData;
    const url_zones = `http://${trolleyUrl}:${port}/fetch_zones?cluster_type=eks&region_name=${location}`;
    try {
      const response = await fetch(url_zones);
      if (!response.ok){
        const error = response.statusText;
        throw new Error(error);
      }
      const zones = await response.json();
      this.setState({ zones });
    } catch(error) {
      console.log(error);
    } finally {
      this.setState({ zonesIsLoading: false })
    }
  }

  async getSubnets(zone) {
    const { trolleyUrl, port } = this.props.appData;
    const url_subnets = `http://${trolleyUrl}:${port}/fetch_subnets?cluster_type=eks&zone_names=${zone}`;
    try {
      const response = await fetch(url_subnets);
      if (!response.ok){
        const error = response.statusText;
        throw new Error(error);
      }
      const subnets = await response.json();
      this.setState({ subnets });
    } catch(error) {
      console.log(error);
    } finally {
      this.setState({ subnetsIsLoading: false })
    }
  }

  populateLocations() {
    return(
      this.state.locations.map((item) => (
        <option value={item}>{item}</option>
      ))
    );
  }

  populateZones() {
    return(
      this.state.zones.map((item) => (
        <option value={item}>{item}</option>
      ))
    );
  }

  populateSubnets() {
    return(
      this.state.subnets.map((item) => (
        <option value={item}>{item}</option>
      ))
    );
  }

  populateHelmInstalls() {
    return(
      this.state.helmInstalls.map((item) => (
        <option value={item}>{item}</option>
      ))
    );
  }

  displayLoading() {
    return (<span className="input-group-text" style={{flex: '1 1 auto'}}><div className="spinner-border  spinner-border-sm mx-auto"></div></span>);
  }

  handleNodesAmtChange = (e) => {
    this.setState({ nodesAmt: e.target.value });
  }

  handleVersionChange = (e) => {
    this.setState({ version: e.target.value });
  }

  handleLocationChange = (e) => {
    this.setState({ location: e.target.value, zonesIsLoading: true });
    this.getZones(e.target.value);
  }

  handleZonesChange = (e) => {
    const selectedZones = [...e.target.selectedOptions].map(opt => opt.value);
    this.setState({ zone: selectedZones, subnetsIsLoading: true });
    this.getSubnets(selectedZones);
  }

  handleSubnetsChange = (e) => {
    this.setState({ subnet: [...e.target.selectedOptions].map(opt => opt.value) });
  }

  handleHelmInstallsChange = (e) => {
    this.setState({ helmInstall: [...e.target.selectedOptions].map(opt => opt.value) });
  }

  handleExpirationTimeChange = (e) => {
    this.setState({ expirationTime: e.target.value });
  }

  handleYamlChange = ({ json, text }) => {
    this.setState({ deploymentYAML: text });
  }

  handleYamlError = (error) => {
    console.log(error);
  }

  uploadYamlFile = (file) => {
    let fileReader = new FileReader();
    fileReader.onloadend = this.handleYamlUpload;
    fileReader.readAsText(file)
  }

  handleYamlUpload = (e) => {
    const content = e.target.result;
    const toastMessage = `Yaml file successfully uploaded`;
    this.setState({ deploymentYAML: content, toastMessage });
    const toastEl = document.getElementById('toast');
    const toast = new Toast(toastEl);
    toast.show();
  }

  buildCluster = async (event) => {
    event.preventDefault();
    const { nodesAmt, version, expirationTime, location, zone, subnet, helmInstall, deploymentYAML } = this.state;
    const { trolleyUrl, port, userName } = this.props.appData;

    if (zone.length < 2){
      alert("Please choose at least 2 zones");
      return
    }

    const triggerData = JSON.stringify({
      "user_name": userName,
      "num_nodes": nodesAmt,
      "version": version,
      "expiration_time": expirationTime,
      "eks_location": location,
      "eks_zones": zone,
      "eks_subnets": subnet,
      "helm_installs": helmInstall,
      "deployment_yaml": deploymentYAML
    });
    console.log(triggerData);

    const url = `http://${trolleyUrl}:${port}/trigger_eks_deployment`;
    let toastMessage = `An EKS deployment was requested for ${version} kubernetes version with ${expirationTime} expiration time`;
    const options = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: triggerData
    };
    try {
      const response = await fetch(url, options);
      if (!response.ok){
        const error = await response.text();
        throw new Error(error);
      }
      const json = await response.json();  
    } catch(error) {
      console.log(error);
      toastMessage = `Error: ${error}`;
    } finally {
      this.setState({ toastMessage });
      const toastEl = document.getElementById('toast');
      const toast = new Toast(toastEl);
      toast.show();
    }
  }

  render() {
    const submitDisabled = this.state.locationsIsLoading
                        || this.state.zonesIsLoading
                        || this.state.subnetsIsLoading
                        || this.state.helmInstallsIsLoading;
    return (
      <div className="col text-center">
        <h2 className="mt-4 mb-4">Build an EKS cluster</h2>
        <div className="row justify-content-md-center">
          <form onSubmit={this.buildCluster} className="col-lg-6 col-md-8">
            <div className="input-group mt-3 mb-3">
              <label className="input-group-text input-color" htmlFor="nodes-amt" style={{ paddingRight: '26px' }}>Select the amount of nodes</label>
              <select
                className="form-select"
                value={this.state.nodesAmt}
                onChange={this.handleNodesAmtChange}
                id="nodes-amt"
                required
              >
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="4">4</option>
                <option value="5">5</option>
              </select>
            </div>
            <div className="input-group mt-3 mb-3">
              <label className="input-group-text input-color" htmlFor="versions-dropdown">Select the Kubernetes version</label>
              <select
                className="form-select"
                value={this.state.version}
                onChange={this.handleVersionChange}
                id="versions-dropdown"
                required
              >
                <option value="1.21">1.21</option>
                <option value="1.20">1.20</option>
                <option value="1.19">1.19</option>
                <option value="1.18">1.18</option>
              </select>
            </div>
            <div className="input-group mt-3 mb-3">
              <label className="input-group-text input-color" htmlFor="locations" style={{ paddingRight: '118px' }}>Select location</label>
              {this.state.locationsIsLoading ?
                this.displayLoading() :
                <select
                  className="form-select"
                  value={this.state.location}
                  onChange={this.handleLocationChange}
                  id="locations"
                  required
                >
                  <option value=""></option>
                  { this.populateLocations() }
                </select>
              }
            </div>
            <div className="input-group mt-3 mb-3">
              <label className="input-group-text input-color" htmlFor="zones" style={{ paddingRight: '7px' }}>Select Zones (Select at least 2)</label>
              {this.state.zonesIsLoading ?
                this.displayLoading() :
                <select multiple
                  className="form-select"
                  value={this.state.zone}
                  onChange={this.handleZonesChange}
                  id="zones"
                  required
                >
                  { this.populateZones() }
                </select>
              }
            </div>
            <div className="input-group mt-3 mb-3">
              <label className="input-group-text input-color" htmlFor="subnets" style={{ paddingRight: '118px' }}>Select Subnets</label>
              {this.state.subnetsIsLoading ?
                this.displayLoading() :
                <select multiple
                  className="form-select"
                  value={this.state.subnet}
                  onChange={this.handleSubnetsChange}
                  id="subnets"
                  required
                >
                  { this.populateSubnets() }
                </select>
              }
            </div>
            <div className="input-group mt-3 mb-3">
              <label className="input-group-text input-color" htmlFor="helm-installs" style={{ paddingRight: '48px' }}>Select Helm Installations</label>
              {this.state.helmInstallsIsLoading ?
                this.displayLoading() :
                <select multiple
                  className="form-select"
                  value={this.state.helmInstall}
                  onChange={this.handleHelmInstallsChange}
                  id="helm-installs"
                  required
                >
                  { this.populateHelmInstalls() }
                </select>
              }
            </div>
            <div className="input-group mt-3 mb-3">
              <label className="input-group-text input-color" htmlFor="expiration-time" style={{ paddingRight: '39px'}}>Select the expiration time</label>
              <select
                className="form-select"
                value={this.state.expirationTime}
                onChange={this.handleExpirationTimeChange}
                id="expiration-time"
                required
              >
                <option value="1">1h</option>
                <option value="2">2h</option>
                <option value="4">4h</option>
                <option value="8">8h</option>
                <option value="12">12h</option>
                <option value="24">24h</option>
                <option value="48">2d</option>
                <option value="96">4d</option>
                <option value="168">7d</option>
                <option value="336">14d</option>
                <option value="720">30d</option>
              </select>
            </div>
            <button data-bs-toggle="collapse" data-bs-target="#yml" className="btn input-color me-2 mb-2">Yaml editor</button>
            <label htmlFor="fileUpload" className="btn input-color mb-2">Upload Yaml file</label>
            <input type="file" accept=".yaml,.yml" onChange={(e) => this.uploadYamlFile(e.target.files[0])} id="fileUpload" style={{display: 'none'}} />
            <br />
            <div id="yml" className="collapse">
              <div style={{backgroundColor: 'white', textAlign: 'left', width: '100%' }}>
                <YamlEditor text={this.state.deploymentYAML} onChange={this.handleYamlChange} onError={this.handleYamlError} />
                {/* <YamlEditor text={this.state.deploymentYAML} onChange={this.handleYamlChange} theme={oneDark} /> */}
              </div>
              {/* <button className="btn input-color mt-1">Save yaml file</button> */}
            </div>

            <button type="submit" className="btn btn-outline-light mb-2 mt-2" id="build-cluster-button" disabled={submitDisabled}>Build Cluster!</button>
          </form>
        </div>
        <div className="toast-container position-absolute top-0 end-0 p-3">
          <div className="toast" id="toast" role="alert" aria-atomic="true" data-bs-delay="5000">
            <div className="toast-header">
              { this.state.toastMessage }
              <button type="button" className="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}

export default CreateCluster;
import './App.css';
import React, { Component } from "react";
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import AppLayout from './components/appLayout';
import ShowClusters from './components/showClusters';
import BuildAKSCluster from './components/buildAKSCluster';
import BuildEKSCluster from './components/buildEKSCluster';
import BuildGKECluster from './components/buildGKECluster';
import PickCluster from './components/pickCluster';
import Login from './components/login';
import Register from './components/register';

class App extends Component {

  constructor() {
    super();
    let data = {};
    let debug = true;
    if (document.getElementById('data').textContent == "{{ data|default({})|tojson }}") {
      // remote server, data can't pass through render_template
      data = {first_name: 'Einat', user_name: 'einatsoferman'};
      //data = {first_name: 'Mike', user_name: 'miketyson'};
      debug = false;
    } else {
      // local server
      data = JSON.parse(document.getElementById('data').textContent);
    }
    const trolleyRemoteUrl = '34.123.171.234';
    const trolleyLocalUrl = 'localhost';
    
    this.state = {
      userName: data.user_name,
      firstName: data.first_name,
      trolleyUrl: debug ? trolleyLocalUrl : trolleyRemoteUrl,
      port: 8081
    };
  }

  render() {
    const data = this.state;
    return (
      <div className="container-fluid min-vh-100 d-flex flex-column">
        <Router>
          <Routes>
            <Route element={<AppLayout appData={data} />}>
              <Route path="/" element={<PickCluster appData={data} />} />
              <Route path="/index" element={<PickCluster appData={data} />} />
              <Route path="/build-aks-clusters" element={<BuildAKSCluster appData={data} />} />
              <Route path="/build-eks-clusters" element={<BuildEKSCluster appData={data} />} />
              <Route path="/build-gke-clusters" element={<BuildGKECluster appData={data} />} />
              <Route path="/manage-aks-clusters" element={<ShowClusters appData={data} type="aks" />} />
              <Route path="/manage-eks-clusters" element={<ShowClusters appData={data} type="eks" />} />
              <Route path="/manage-gke-clusters" element={<ShowClusters appData={data} type="gke" />} />
            </Route>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
          </Routes>
        </Router>
      </div>
    );
  } 
}

export default App;
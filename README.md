# Domino CDK EKS Stack

### **DEPRECATED:** This Domino CDK EKS stack automation is not compatible with Kubernetes version 1.25 and onwards. It is recommended that you migrate your automation to [Terraform](https://github.com/dominodatalab/terraform-aws-eks) using the [CDK to Terraform](./convert/) utility.
## Contents

* cdk/ - Python CDK project for deploying an EKS cluster for use with Domino.
* terraform/ - Terraform module for deploying CDK-created CloudFormation. Can be used as an example of how to deploy CDK-created CloudFormation without the CDK cli tool, ie for use in automation etc., and manual instructions included in README.

## Bootstrapping

### Setting up CDK

To work with CDK, you'll need to install nodejs (and npm if it's a separate package on your operating system) if you don't have it already:

    brew install node@14
    sudo apt install npm
    sudo yum install nodejs
    etc.

Then install aws-cdk via npm. Currently we're standardized on 1.153.1:

    npm install -g aws-cdk@1.153.1 # This may require sudo

### Setting up your Python environment

You'll need to have Python 3.9. There are stock instructions for setting up a virtualenv in the README.md file in the `cdk/` subdirectory. You can optionally use a Pipenv to manage this instead, which will pick up the requirements.txt automatically.
